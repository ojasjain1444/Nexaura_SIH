"""
Demo chat responder — Python port of the frontend's existing keyword-match
mock (src/data/mockChat.ts's findMockResponse).

THIS IS NOT AI. THIS IS NOT RAG. It is the same clearly-labelled
placeholder logic the frontend has used since the prototype phase, moved
server-side so that chat can be persisted end-to-end without pretending an
LLM is involved. Do not extend this file to call any AI provider — that is
explicitly Phase 4/5 work, not Phase 2.
"""

_RESPONSES: list[tuple[list[str], str]] = [
    (
        ["drinking water", "bottle", "packaged water"],
        "Packaged drinking water (other than natural mineral water) sold in India must conform to IS 14625. "
        "This standard covers permissible limits for physical, chemical, and microbiological parameters, along "
        "with labelling requirements. Products in this category require mandatory BIS certification before sale.",
    ),
    (
        ["electric kettle", "household appliance", "electrical appliance"],
        "Electric kettles fall under household electrical appliances and are governed by IS 302-1 (general safety "
        "requirements) along with the applicable Part 2 standard for the specific appliance type. Sale in India "
        "requires registration under the Compulsory Registration Scheme (CRS) after testing at a BIS-recognized lab.",
    ),
    (
        ["isi mark", "isi license", "product certification", "certification process"],
        "To obtain an ISI Mark license: (1) submit an application with product and factory details, (2) undergo a "
        "factory evaluation by BIS officers, (3) have product samples tested against the applicable Indian "
        "Standard, and (4) receive the license upon satisfactory evaluation. The average duration is around 90 days.",
    ),
    (
        ["hallmark", "hallmarking", "gold jewellery", "gold purity"],
        "Gold jewellery hallmarking in India is governed by IS 15885. Jewellers must register under the BIS "
        "Hallmarking Scheme, and items are tested for purity at a registered Assaying & Hallmarking Centre (AHC) "
        "before receiving a hallmark with a unique HUID. Permitted fineness grades include 22K916, 18K750, and 14K585.",
    ),
    (
        ["lab", "laboratory", "testing", "plastics testing", "chennai"],
        "Here are BIS-recognized testing laboratories that may be relevant based on your query. You can filter by "
        "test category, city, and accreditation type in the Lab Directory for a complete list with contact details.",
    ),
    (
        ["verify", "genuine", "fake", "complaint", "consumer"],
        "You can verify an ISI/hallmark license by checking the license number against the BIS database, which "
        "lists the manufacturer, product, and validity status. If you suspect a product is falsely marked, you can "
        "file a complaint through the BIS CARE portal or the National Consumer Helpline.",
    ),
]

_DEFAULT_RESPONSE = (
    "I can help with Indian Standards, certification schemes, hallmarking, testing labs, and consumer queries. "
    'Try asking something like "Which standard applies to my product?"'
)


def generate_demo_response(user_text: str) -> str:
    lower = user_text.lower()
    for keywords, response in _RESPONSES:
        if any(keyword in lower for keyword in keywords):
            return response
    return _DEFAULT_RESPONSE
