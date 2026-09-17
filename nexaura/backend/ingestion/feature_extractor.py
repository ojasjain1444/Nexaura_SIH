"""
feature_extractor.py — Phase 5+7: Feature Extraction (Groups A–F) and KnowledgeUnit

Project: Nexaura (SIH 2026 — SIH26107)

THIS IS THE MOST IMPORTANT MODULE IN THE PIPELINE.

The Nexaura chatbot uses feature-based similarity search.
Every KnowledgeUnit must contain rich, structured features
across all 6 groups (A–F) so that similarity matching can
operate on multiple dimensions simultaneously.

Feature Groups:
    A. Document Features:     standard_number, title, edition, year, part, status
    B. Structural Features:   section, clause, sub_clause, parent_clause, heading, content_type
    C. Semantic Features:     scope, summary, keywords, entities, product, application, material, process
    D. Technical Features:    parameters, values, units, ranges, min/max, grades, classes
    E. Requirement Features:  shall, shall not, must, minimum, maximum, requirement objects
    F. Relationship Features: references, cross_references, supersedes, superseded_by

The KnowledgeUnit Pydantic model is the central data contract.
Every downstream consumer (PostgreSQL, Qdrant, BM25) uses this model.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# =============================================================================
# Sub-models
# =============================================================================

class TechnicalParameter(BaseModel):
    """A single extracted technical parameter."""
    name: str
    value: Optional[float] = None
    value_str: Optional[str] = None     # original string value (preserved)
    unit: Optional[str] = None
    operator: Optional[str] = None      # minimum | maximum | equal | range
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    material: Optional[str] = None
    context: Optional[str] = None       # snippet of source text


class Requirement(BaseModel):
    """A structured requirement extracted from a clause."""
    text: str                           # original requirement wording
    keyword: str                        # shall | must | shall not | minimum | etc.
    subject: Optional[str] = None       # what the requirement applies to
    condition: Optional[str] = None


# =============================================================================
# KnowledgeUnit — central data model
# =============================================================================

class KnowledgeUnit(BaseModel):
    """
    A single searchable knowledge record extracted from a BIS clause.

    This is the fundamental unit of the Nexaura knowledge base.
    Every field is designed to support multi-dimensional similarity search.

    ID format: {std_number_clean}_{year}_{clause}
    Example:   IS1234_2024_5.2.1
    """

    # ---- Identity -----------------------------------------------------------
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique record ID (generated if not provided)",
    )

    # ---- Group A: Document Features -----------------------------------------
    standard_number: str = Field(..., description="IS standard number, e.g. 'IS 456'")
    title: Optional[str] = Field(None, description="Full standard title")
    edition: Optional[str] = Field(None, description="Edition string")
    year: Optional[int] = Field(None, description="Publication year")
    part: Optional[str] = Field(None, description="Part number if applicable")
    amendment: Optional[str] = Field(None, description="Amendment number if applicable")
    status: str = Field("unknown", description="Standard status — never inferred")

    # ---- Group B: Structural Features ---------------------------------------
    section: Optional[str] = Field(None, description="Top-level section name")
    clause: str = Field(..., description="Clause number, e.g. '5.2.1'")
    sub_clause: Optional[str] = Field(None, description="Sub-clause number")
    parent_clause: Optional[str] = Field(None, description="Parent clause number")
    heading: Optional[str] = Field(None, description="Clause heading text")
    content_type: str = Field("clause", description="clause | requirement | definition | note | annex | scope")
    page_start: int = Field(0, description="Starting page number")
    page_end: int = Field(0, description="Ending page number")
    annex: Optional[str] = Field(None, description="Annex identifier if applicable")

    # ---- Content ------------------------------------------------------------
    scope: Optional[str] = Field(None, description="Document scope (for scope-type records)")
    summary: Optional[str] = Field(None, description="Auto-generated summary (max 200 chars)")
    text: str = Field("", description="Processed clean text")
    raw_text: str = Field("", description="Original extracted text (preserved verbatim)")
    clean_text: str = Field("", description="Cleaned text after artifact removal")

    # ---- Group C: Semantic Features -----------------------------------------
    keywords: list[str] = Field(default_factory=list, description="Key terms")
    entities: list[str] = Field(default_factory=list, description="Named entities")
    product: list[str] = Field(default_factory=list, description="Product names")
    application: list[str] = Field(default_factory=list, description="Application domains")
    industry: list[str] = Field(default_factory=list, description="Industry sectors")
    domain: list[str] = Field(default_factory=list, description="Technical domains")
    material: list[str] = Field(default_factory=list, description="Material names")
    process: list[str] = Field(default_factory=list, description="Process names")

    # ---- Group D: Technical Features ----------------------------------------
    technical_parameters: list[TechnicalParameter] = Field(
        default_factory=list,
        description="Extracted numeric/dimensional parameters",
    )

    # ---- Group E: Requirement Features --------------------------------------
    requirements: list[Requirement] = Field(
        default_factory=list,
        description="Structured requirement objects",
    )

    # ---- Group F: Relationship Features ------------------------------------
    references: list[str] = Field(
        default_factory=list,
        description="Referenced standards (evidence-based only)",
    )
    cross_references: list[str] = Field(
        default_factory=list,
        description="Cross-references to other clauses",
    )
    supersedes: Optional[str] = Field(None, description="Standard this supersedes")
    superseded_by: Optional[str] = Field(None, description="Standard that supersedes this")
    amended_by: list[str] = Field(default_factory=list, description="Amendment references")

    # ---- Provenance ---------------------------------------------------------
    source_pdf: str = Field("", description="Source PDF filename")
    extraction_method: str = Field("gemini_flash", description="OCR/extraction method used")
    ocr_confidence: float = Field(0.0, description="Extraction confidence score 0.0–1.0")

    # ---- Quality Flags ------------------------------------------------------
    needs_review: bool = Field(False, description="Flagged for human review")
    validation_status: str = Field("pending", description="valid | flagged | rejected")
    review_reason: Optional[str] = Field(None, description="Reason for review flag")

    # ---- Search Text --------------------------------------------------------
    search_text: str = Field(
        "",
        description="Combined searchable text for BM25 and embedding",
    )

    @field_validator("standard_number")
    @classmethod
    def normalize_std_number(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("status")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        mapping = {
            "in force": "In Force",
            "current":  "In Force",
            "active":   "In Force",
            "revised":  "Revised",
            "withdrawn": "Withdrawn",
            "superseded": "Superseded",
            "reaffirmed": "Reaffirmed",
            "under revision": "Under Revision",
        }
        return mapping.get(v.strip().lower(), v or "unknown")

    def generate_id(self) -> str:
        """Generate a stable, human-readable ID for this record."""
        std_clean = re.sub(r"[^A-Za-z0-9]", "", self.standard_number)
        year_str = str(self.year) if self.year else "XXXX"
        clause_clean = re.sub(r"[^A-Za-z0-9._\-]", "_", self.clause)
        return f"{std_clean}_{year_str}_{clause_clean}"

    def build_search_text(self) -> str:
        """
        Build combined searchable text from all feature groups.
        Used for BM25 indexing and embedding generation.
        """
        parts: list[str] = []

        if self.title:
            parts.append(self.title)
        if self.scope:
            parts.append(self.scope)
        if self.heading:
            parts.append(self.heading)
        if self.clean_text:
            parts.append(self.clean_text)
        elif self.text:
            parts.append(self.text)
        if self.keywords:
            parts.append(" ".join(self.keywords))
        if self.product:
            parts.append(" ".join(self.product))
        if self.application:
            parts.append(" ".join(self.application))
        if self.material:
            parts.append(" ".join(self.material))
        if self.process:
            parts.append(" ".join(self.process))
        if self.entities:
            parts.append(" ".join(self.entities))

        # Include technical parameter names and values
        for param in self.technical_parameters:
            param_text = param.name
            if param.value is not None:
                param_text += f" {param.value}"
            if param.unit:
                param_text += f" {param.unit}"
            if param.operator:
                param_text += f" ({param.operator})"
            parts.append(param_text)

        return " ".join(p for p in parts if p)

    model_config = {"json_schema_extra": {
        "example": {
            "id": "IS1234_2024_5.2.1",
            "standard_number": "IS 1234",
            "title": "Galvanized Steel Pipe",
            "edition": "2024",
            "year": 2024,
            "clause": "5.2.1",
            "heading": "Coating Thickness",
            "text": "The zinc coating shall have a minimum thickness of 80 μm.",
            "product": ["galvanized steel pipe"],
            "material": ["zinc", "steel"],
            "technical_parameters": [
                {"name": "coating thickness", "value": 80, "unit": "μm", "operator": "minimum"}
            ],
            "requirements": [
                {"text": "The zinc coating shall have a minimum thickness of 80 μm.", "keyword": "shall"}
            ],
        }
    }}


# =============================================================================
# Feature Extractor
# =============================================================================

class FeatureExtractor:
    """
    Extracts all feature groups (A–F) from ClauseNode objects and
    constructs KnowledgeUnit records.

    This is the most important module in the pipeline.
    """

    # ---- Group D: Technical parameter patterns -----

    # Matches: "80 μm", "2.5 mm", "450 MPa", "1.2 kg/m²", "25°C"
    VALUE_UNIT_RE = re.compile(
        r"(\d+(?:\.\d+)?)\s*"
        r"(μm|µm|mm|cm|m|km|"
        r"MPa|GPa|kPa|Pa|"
        r"kg(?:/m[²³])?|g(?:/m[²³])?|"
        r"°C|°F|K|"
        r"N(?:/mm[²])?|kN|"
        r"%|‰|"
        r"ml|L|"
        r"Ω|V|A|W|kW|"
        r"rpm|Hz|"
        r"g/cm[³]?|kg/m[³]?)"
    )

    # Matches minimum/maximum language
    LIMIT_RE = re.compile(
        r"(minimum|maximum|not less than|not more than|"
        r"min\.|max\.|at least|at most|"
        r"≥|≤|>|<)\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"([a-zA-Zμµ°/%²³]+)?",
        re.IGNORECASE,
    )

    # Requirement language keywords
    REQUIREMENT_KEYWORDS = [
        "shall not", "shall", "must not", "must",
        "is required to", "is prohibited",
        "minimum", "maximum",
        "not less than", "not more than",
        "permitted", "prohibited",
        "recommended",
    ]

    # Group C: Product/Material/Process dictionaries
    PRODUCTS = [
        "steel pipe", "galvanized pipe", "cast iron pipe", "copper pipe",
        "cement", "concrete", "reinforced concrete", "mortar",
        "steel bar", "steel rod", "steel wire", "steel sheet", "steel plate",
        "galvanized steel", "stainless steel", "alloy steel",
        "structural steel", "mild steel",
        "paint", "coating", "zinc coating", "epoxy coating",
        "cable", "wire rope", "chain", "fastener", "bolt", "nut",
        "valve", "fitting", "flange", "coupling",
        "brick", "tile", "glass", "plastic", "rubber",
        "aluminium", "copper", "brass", "bronze",
        "fuel", "lubricant", "oil", "grease",
    ]

    MATERIALS = [
        "steel", "iron", "zinc", "aluminium", "copper", "brass", "bronze",
        "lead", "tin", "nickel", "chromium", "manganese", "silicon",
        "concrete", "cement", "sand", "aggregate", "gravel",
        "wood", "timber", "glass", "plastic", "rubber", "polymer",
        "asbestos", "fibre", "fabric", "textile",
        "bitumen", "asphalt", "epoxy", "polyurethane",
        "carbon", "graphite", "ceramic", "porcelain",
    ]

    PROCESSES = [
        "galvanizing", "galvanization", "hot-dip galvanizing",
        "welding", "casting", "forging", "rolling", "drawing",
        "tempering", "annealing", "hardening", "quenching",
        "coating", "painting", "plating", "electroplating",
        "testing", "sampling", "inspection", "certification",
        "mixing", "curing", "compaction", "compression",
    ]

    APPLICATIONS = [
        "water supply", "water distribution", "drinking water",
        "sewage", "drainage", "irrigation",
        "gas supply", "oil pipeline",
        "structural", "construction", "building", "bridge",
        "electrical", "power transmission",
        "underground", "buried", "submerged",
        "high temperature", "low temperature",
        "corrosive environment", "marine",
        "highway", "road", "pavement",
        "pressure", "high pressure",
        "fire fighting", "sprinkler",
    ]

    INDUSTRIES = [
        "construction", "civil engineering", "structural engineering",
        "plumbing", "piping", "pipeline",
        "electrical", "electronics",
        "automotive", "transportation",
        "chemical", "petrochemical",
        "food", "pharmaceutical",
        "mining", "metallurgy",
        "agriculture", "irrigation",
        "defence", "aerospace",
    ]

    PROPERTY_KEYWORDS = {
        "coating thickness": ["coating thickness", "coat thickness", "thickness of coating"],
        "tensile strength": ["tensile strength", "ultimate tensile", "UTS"],
        "yield strength": ["yield strength", "yield stress", "proof stress"],
        "elongation": ["elongation", "elongation at break", "percentage elongation"],
        "hardness": ["hardness", "Brinell hardness", "Vickers hardness", "Rockwell"],
        "impact strength": ["impact strength", "Charpy", "Izod"],
        "density": ["density", "specific gravity", "mass per unit"],
        "chemical composition": ["chemical composition", "chemical analysis", "chemical requirement"],
        "carbon content": ["carbon content", "carbon percentage", "%C"],
        "zinc coating mass": ["coating mass", "zinc mass", "mass of coating", "g/m2", "g/m²"],
        "water absorption": ["water absorption", "absorption"],
        "compressive strength": ["compressive strength", "crushing strength"],
        "flexural strength": ["flexural strength", "bending strength"],
        "pH": ["pH", "hydrogen ion"],
        "temperature": ["temperature", "°C", "°F"],
        "pressure": ["pressure", "working pressure", "burst pressure"],
        "dimension": ["dimension", "dimensional", "size", "length", "width", "height", "diameter"],
        "tolerance": ["tolerance", "permissible variation", "allowed deviation"],
        "weight": ["weight", "mass per metre", "linear mass"],
    }

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def extract(
        self,
        clause_node,          # ClauseNode from clause_parser
        document_meta,        # DocumentMetadata from metadata_extractor
        source_pdf: str,
        ocr_confidence: float = 0.95,
    ) -> KnowledgeUnit:
        """
        Extract all features from a ClauseNode and build a KnowledgeUnit.

        Args:
            clause_node:     ClauseNode with raw_text and structural data
            document_meta:   DocumentMetadata for document-level context
            source_pdf:      Source PDF filename
            ocr_confidence:  Confidence score from Gemini or text extraction

        Returns:
            KnowledgeUnit with all feature groups populated
        """
        text = clause_node.raw_text or clause_node.text or ""
        text_lower = text.lower()

        # --- Group C: Semantic features ---
        keywords  = self._extract_keywords(text)
        entities  = self._extract_entities(text)
        products  = self._extract_from_vocabulary(text_lower, self.PRODUCTS)
        materials = self._extract_from_vocabulary(text_lower, self.MATERIALS)
        processes = self._extract_from_vocabulary(text_lower, self.PROCESSES)
        apps      = self._extract_from_vocabulary(text_lower, self.APPLICATIONS)
        industries= self._extract_from_vocabulary(text_lower, self.INDUSTRIES)

        # Also extract from heading
        if clause_node.heading:
            h_lower = clause_node.heading.lower()
            products  = list(set(products  + self._extract_from_vocabulary(h_lower, self.PRODUCTS)))
            materials = list(set(materials + self._extract_from_vocabulary(h_lower, self.MATERIALS)))
            processes = list(set(processes + self._extract_from_vocabulary(h_lower, self.PROCESSES)))

        # --- Group D: Technical features ---
        tech_params = self._extract_technical_parameters(text)

        # --- Group E: Requirements ---
        requirements = self._extract_requirements(text)

        # --- Group F: Relationships ---
        cross_refs = self._extract_cross_references(text)

        # Build summary (max 200 chars from text)
        summary = self._build_summary(text)

        # Scope (only for scope-type clauses)
        scope_text = (
            document_meta.scope
            if clause_node.content_type == "scope"
            else None
        )

        # Determine standard number with source_pdf fallback
        std_num = document_meta.standard_number if (document_meta and document_meta.standard_number != "unknown") else ""
        if not std_num and source_pdf:
            m = re.search(r"(?:IS|I\.S\.)\s*(\d+)", source_pdf.replace("_", " "), re.IGNORECASE)
            if m:
                std_num = f"IS {m.group(1)}".upper()
        std_num = std_num or "unknown"

        # Build KnowledgeUnit
        ku = KnowledgeUnit(
            # Group A
            standard_number=std_num,
            title=document_meta.title or source_pdf.replace(".pdf", ""),
            edition=document_meta.edition,
            year=document_meta.year,
            part=document_meta.part,
            amendment=document_meta.amendment,
            status=document_meta.status,

            # Group B
            section=clause_node.section,
            clause=clause_node.clause,
            sub_clause=clause_node.sub_clause,
            parent_clause=clause_node.parent_clause,
            heading=clause_node.heading,
            content_type=clause_node.content_type,
            page_start=clause_node.page_start,
            page_end=clause_node.page_end,
            annex=clause_node.annex,

            # Content
            scope=scope_text or document_meta.scope if clause_node.content_type == "scope" else None,
            text=text,
            raw_text=text,  # cleaner.py will set clean_text later

            # Group C
            keywords=keywords,
            entities=entities,
            product=products,
            application=apps,
            industry=industries,
            material=materials,
            process=processes,

            # Group D
            technical_parameters=tech_params,

            # Group E
            requirements=requirements,

            # Group F
            references=document_meta.references,
            cross_references=cross_refs,
            supersedes=document_meta.supersedes,
            superseded_by=document_meta.superseded_by,
            amended_by=document_meta.amended_by,

            # Provenance
            source_pdf=source_pdf,
            extraction_method="gemini_flash",
            ocr_confidence=ocr_confidence,
            needs_review=clause_node.raw_text == "" or ocr_confidence < 0.70,
        )

        # Generate stable ID
        ku.id = ku.generate_id()

        # Build summary
        ku.summary = summary

        # Build search text
        ku.search_text = ku.build_search_text()

        return ku

    # -------------------------------------------------------------------------
    # Group C: Semantic Feature Helpers
    # -------------------------------------------------------------------------

    def _extract_from_vocabulary(self, text: str, vocab: list[str]) -> list[str]:
        """Extract all vocabulary items found in text."""
        found = []
        for item in vocab:
            if item.lower() in text:
                found.append(item)
        return found

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract important technical keywords from clause text."""
        # Remove stop words and extract meaningful terms
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had",
            "this", "that", "these", "those", "it", "its",
            "shall", "should", "may", "must", "will",
        }
        # Extract words that are capitalized or contain digits (likely technical)
        words = re.findall(r"[A-Z][a-z]+|[A-Za-z]+\d+|\d+[A-Za-z]+", text)
        keywords = list({w.lower() for w in words if w.lower() not in stop_words and len(w) > 2})
        return keywords[:20]  # Limit to 20 keywords

    def _extract_entities(self, text: str) -> list[str]:
        """Extract named entities (standards, product names, proper nouns)."""
        entities = []

        # IS standard references
        is_refs = re.findall(r"\bIS\s+\d+(?:\s*:\s*\d{4})?\b", text)
        entities.extend(is_refs)

        # Other standard bodies
        std_refs = re.findall(r"\b(?:BS|ASTM|ISO|EN|DIN|JIS)\s*[\d\w\-]+\b", text)
        entities.extend(std_refs)

        # Chemical symbols/formulas
        chem = re.findall(r"\b[A-Z][a-z]?\d*(?:\.[A-Z][a-z]?\d*)*\b", text)
        chem_filtered = [c for c in chem if len(c) <= 10 and any(c[0] in "CHNOSPMFZN" for c in [c])]
        entities.extend(chem_filtered)

        return list(set(entities))[:15]

    # -------------------------------------------------------------------------
    # Group D: Technical Feature Extraction
    # -------------------------------------------------------------------------

    def _extract_technical_parameters(self, text: str) -> list[TechnicalParameter]:
        """
        Extract numeric technical parameters from clause text.

        Examples handled:
            "minimum thickness of 80 μm"
            → {name: "coating thickness", value: 80, unit: "μm", operator: "minimum"}

            "tensile strength not less than 450 MPa"
            → {name: "tensile strength", value: 450, unit: "MPa", operator: "minimum"}
        """
        params: list[TechnicalParameter] = []
        sentences = re.split(r"[.;]\s+", text)

        for sentence in sentences:
            sentence_lower = sentence.lower()

            # Find operator
            operator = None
            if re.search(r"\bminimum\b|not less than|at least|≥", sentence_lower):
                operator = "minimum"
            elif re.search(r"\bmaximum\b|not more than|at most|≤", sentence_lower):
                operator = "maximum"

            # Find value+unit pairs
            value_matches = self.VALUE_UNIT_RE.finditer(sentence)
            for match in value_matches:
                try:
                    value = float(match.group(1))
                    unit = match.group(2)
                except ValueError:
                    continue

                # Determine parameter name from context
                param_name = self._identify_parameter_name(sentence_lower)

                if param_name:
                    params.append(TechnicalParameter(
                        name=param_name,
                        value=value,
                        value_str=match.group(0),
                        unit=unit,
                        operator=operator,
                        context=sentence[:150],
                    ))

            # Limit parameter check
            limit_matches = self.LIMIT_RE.finditer(sentence)
            for match in limit_matches:
                op_word = match.group(1).strip().lower()
                val_str = match.group(2)
                unit_str = match.group(3) or ""

                op = "minimum" if op_word in ("minimum", "min.", "not less than", "at least", "≥") else "maximum"

                try:
                    value = float(val_str)
                except ValueError:
                    continue

                param_name = self._identify_parameter_name(sentence_lower)
                if param_name and not any(p.name == param_name and p.value == value for p in params):
                    params.append(TechnicalParameter(
                        name=param_name,
                        value=value,
                        value_str=f"{val_str} {unit_str}".strip(),
                        unit=unit_str.strip() or None,
                        operator=op,
                        context=sentence[:150],
                    ))

        return params[:10]  # Maximum 10 parameters per clause

    def _identify_parameter_name(self, text_lower: str) -> Optional[str]:
        """Identify the property being measured from clause text."""
        for prop_name, patterns in self.PROPERTY_KEYWORDS.items():
            if any(p.lower() in text_lower for p in patterns):
                return prop_name
        return None

    # -------------------------------------------------------------------------
    # Group E: Requirement Extraction
    # -------------------------------------------------------------------------

    def _extract_requirements(self, text: str) -> list[Requirement]:
        """
        Extract structured requirement objects from clause text.

        Preserves original wording — never rewrites requirements.
        """
        requirements: list[Requirement] = []
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Find the first matching requirement keyword
            matched_keyword = None
            for kw in self.REQUIREMENT_KEYWORDS:
                pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
                if pattern.search(sentence):
                    matched_keyword = kw
                    break

            if matched_keyword and len(sentence) >= 10:
                requirements.append(Requirement(
                    text=sentence,
                    keyword=matched_keyword.lower(),
                ))

        return requirements[:20]  # Max 20 requirements per clause

    # -------------------------------------------------------------------------
    # Group F: Cross-reference Extraction
    # -------------------------------------------------------------------------

    def _extract_cross_references(self, text: str) -> list[str]:
        """Extract clause cross-references from text."""
        # Match patterns like "see 5.2", "refer to 5.2.1", "(see Table 3)"
        refs = re.findall(
            r"(?:see|refer to|as per|in accordance with)\s+"
            r"((?:\d+(?:\.\d+)*)|(?:Table\s+\d+)|(?:Annex\s+[A-Z]))",
            text,
            re.IGNORECASE,
        )
        return list(set(refs))

    # -------------------------------------------------------------------------
    # Summary generation
    # -------------------------------------------------------------------------

    def _build_summary(self, text: str, max_chars: int = 200) -> str:
        """Build a short summary from clause text."""
        if not text:
            return ""
        # Take first complete sentence(s) up to max_chars
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary_parts: list[str] = []
        length = 0
        for s in sentences:
            if length + len(s) > max_chars:
                break
            summary_parts.append(s)
            length += len(s)
        return " ".join(summary_parts)[:max_chars]
