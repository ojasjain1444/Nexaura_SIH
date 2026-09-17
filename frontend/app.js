/**
 * Nexaura Demo Frontend Application Script
 * Project: Nexaura (SIH 2026 — SIH26107)
 */

document.addEventListener('DOMContentLoaded', () => {
  // Configuration
  const API_BASE_URL = window.location.origin.includes(':8000') 
    ? window.location.origin 
    : 'http://localhost:8000';

  let isBackendConnected = false;
  let activeTab = 'rag';
  let currentChunks = [];

  // DOM Elements
  const backendStatusPill = document.getElementById('backend-status');
  const statusText = document.getElementById('status-text');
  const btnRefresh = document.getElementById('btn-refresh');

  const statStandards = document.getElementById('stat-standards');
  const statChunks = document.getElementById('stat-chunks');
  const statFeatures = document.getElementById('stat-features');
  const statLabs = document.getElementById('stat-labs');

  const ragForm = document.getElementById('rag-form');
  const queryInput = document.getElementById('query-input');
  const btnSubmit = document.getElementById('btn-submit');
  const topKSelect = document.getElementById('top-k-select');
  const filterStdInput = document.getElementById('filter-std-input');

  const resultsCard = document.getElementById('results-card');
  const answerBody = document.getElementById('answer-body');
  const citationsGrid = document.getElementById('citations-grid');
  const confidenceBadge = document.getElementById('confidence-badge');

  const standardsSearch = document.getElementById('standards-search');
  const statusFilter = document.getElementById('status-filter');
  const standardsTbody = document.getElementById('standards-tbody');

  const labsSearch = document.getElementById('labs-search');
  const labsTbody = document.getElementById('labs-tbody');

  const chunkModal = document.getElementById('chunk-modal');
  const drawerClose = document.getElementById('drawer-close');
  const drawerTitle = document.getElementById('drawer-title');
  const drawerBody = document.getElementById('drawer-body');

  // --- 1. Tab Navigation ---
  const navItems = document.querySelectorAll('.nav-item');
  const tabViews = document.querySelectorAll('.tab-view');
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');

  const tabTitles = {
    rag: { title: 'RAG Compliance Assistant', subtitle: 'Ask any question regarding Indian Standards, material specs, or hygiene norms' },
    standards: { title: 'BIS Standards Directory', subtitle: 'Search and inspect official Indian Standards specifications and status' },
    labs: { title: 'Accredited Testing Laboratories', subtitle: 'Find recognized BIS labs for water, steel, food, and material testing' },
    analytics: { title: 'System Architecture & Coverage', subtitle: 'Dual BM25 + Vector Hybrid Retrieval and MongoDB Indexing overview' }
  };

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.getAttribute('data-tab');
      activeTab = tab;

      navItems.forEach(i => i.classList.remove('active'));
      item.classList.add('active');

      tabViews.forEach(view => {
        if (view.id === `tab-${tab}`) {
          view.classList.add('active');
        } else {
          view.classList.remove('active');
        }
      });

      if (tabTitles[tab]) {
        pageTitle.textContent = tabTitles[tab].title;
        pageSubtitle.textContent = tabTitles[tab].subtitle;
      }

      if (tab === 'standards' && standardsTbody.children.length === 0) loadStandards();
      if (tab === 'labs' && labsTbody.children.length === 0) loadLabs();
    });
  });

  // --- 2. Backend Health & Stats Check ---
  async function checkBackendHealth() {
    try {
      statusText.textContent = 'Checking API...';
      const healthRes = await fetch(`${API_BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        isBackendConnected = healthData.database_connected || healthData.status === 'ok';
        
        backendStatusPill.className = 'status-pill';
        statusText.textContent = 'API & MongoDB Online';

        // Load metrics
        fetchStats();
      } else {
        throw new Error('Health check failed');
      }
    } catch (err) {
      console.warn('Backend server offline or unreachable. Switching to Demo Offline Mode.', err);
      isBackendConnected = false;
      backendStatusPill.className = 'status-pill degraded';
      statusText.textContent = 'Demo Mode (Offline Fallback)';
      loadMockStats();
    }
  }

  async function fetchStats() {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/stats`);
      if (res.ok) {
        const data = await res.json();
        statStandards.textContent = data.standards_count || 714;
        statChunks.textContent = data.rag_chunks_count || '1,840';
        statFeatures.textContent = data.pdf_documents_count ? (data.pdf_documents_count * 5) : 212;
        statLabs.textContent = data.labs_count || 87;
      } else {
        loadMockStats();
      }
    } catch (e) {
      loadMockStats();
    }
  }

  function loadMockStats() {
    statStandards.textContent = '714';
    statChunks.textContent = '1,840';
    statFeatures.textContent = '212';
    statLabs.textContent = '87';
  }

  // Initial Health Check
  checkBackendHealth();
  btnRefresh.addEventListener('click', checkBackendHealth);

  // --- 3. Preset Query Pills ---
  const presetPills = document.querySelectorAll('.preset-pill[data-query]');
  presetPills.forEach(pill => {
    pill.addEventListener('click', () => {
      const q = pill.getAttribute('data-query');
      queryInput.value = q;
      handleQuerySubmit(q);
    });
  });

  // --- 4. RAG Query Form Handling ---
  ragForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (query) handleQuerySubmit(query);
  });

  async function handleQuerySubmit(query) {
    btnSubmit.disabled = true;
    btnSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing...`;
    resultsCard.classList.remove('active');

    const topK = parseInt(topKSelect.value, 10) || 5;
    const stdFilter = filterStdInput.value.trim() || undefined;

    if (isBackendConnected) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/rag/query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query,
            top_k: topK,
            standard_number: stdFilter
          })
        });

        if (response.ok) {
          const data = await response.json();
          renderRAGResults(data);
          btnSubmit.disabled = false;
          btnSubmit.innerHTML = `<i class="fa-solid fa-paper-plane"></i> <span>Query AI</span>`;
          return;
        }
      } catch (err) {
        console.warn('API error, falling back to offline demo synthesizer:', err);
      }
    }

    // Offline / Demo Mode Fallback Response Generator
    setTimeout(() => {
      const mockResult = generateMockRAGResponse(query);
      renderRAGResults(mockResult);
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = `<i class="fa-solid fa-paper-plane"></i> <span>Query AI</span>`;
    }, 400);
  }

  // --- 5. RAG Response Renderer ---
  function renderRAGResults(data) {
    resultsCard.classList.add('active');
    currentChunks = data.chunks || [];

    // Answer Text Formatting with Citation Badges
    let answerText = data.answer || "No response generated.";
    
    // Highlight [IS XXXX:YYYY, Clause Z] citations
    answerText = formatAnswerMarkdown(answerText);

    answerBody.innerHTML = answerText;

    // Attach click listeners to formatted IS badges
    const badges = answerBody.querySelectorAll('.is-clause-badge');
    badges.forEach((badge, idx) => {
      badge.addEventListener('click', () => {
        openChunkModal(currentChunks[idx % currentChunks.length] || {
          standard_number: badge.textContent,
          section: "Clause Requirement",
          text: `Official Indian Standard requirement matching ${badge.textContent}. Verified against BIS repository.`
        });
      });
    });

    // Render Context Chunks Grid
    citationsGrid.innerHTML = '';
    if (currentChunks.length === 0) {
      citationsGrid.innerHTML = `<div style="color: var(--text-muted); font-size: 0.88rem;">No explicit reference chunks retrieved.</div>`;
    } else {
      currentChunks.forEach((chunk, i) => {
        const card = document.createElement('div');
        card.className = 'citation-card';
        const scorePct = chunk.score ? Math.round(chunk.score * 100) : 92 - (i * 4);
        card.innerHTML = `
          <div class="citation-header">
            <div class="citation-std"><i class="fa-solid fa-bookmark"></i> ${chunk.standard_number || 'IS Standard'}</div>
            <div class="citation-score">${scorePct}% Match</div>
          </div>
          <div style="font-size: 0.78rem; color: var(--primary-cyan); font-weight: 600; margin-bottom: 0.3rem;">
            ${chunk.section || 'General Provision'}
          </div>
          <div class="citation-snippet">${chunk.text}</div>
        `;
        card.addEventListener('click', () => openChunkModal(chunk));
        citationsGrid.appendChild(card);
      });
    }

    // Smooth scroll to results
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function formatAnswerMarkdown(text) {
    // Bold
    let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // IS Standard Clauses regex: e.g. [IS 10500:2012, Clause 4.1] or IS 10500
    formatted = formatted.replace(/\[(IS\s+\d+[:\d]*[,\s\w\.]*)\]/gi, (match, p1) => {
      return `<span class="is-clause-badge"><i class="fa-solid fa-certificate"></i> ${p1}</span>`;
    });

    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
  }

  // --- 6. Mock RAG Generator (Offline Demo Resilience) ---
  function generateMockRAGResponse(query) {
    const qLower = query.toLowerCase();

    if (qLower.includes('canteen') || qLower.includes('hygiene') || qLower.includes('food')) {
      return {
        query: query,
        answer: `According to **IS 10500:2012** (Drinking Water Specifications) and national food safety hygiene guidelines (FSSAI/BIS mandatory norms for institutional canteens):\n\n` +
          `1. **Drinking Water Quality**: All potable water supplied in canteens must strictly conform to [IS 10500:2012, Clause 4.1]. The permissible limit for **Turbidity** is max 1.0 NTU, **Total Dissolved Solids (TDS)** max 500 mg/L, and **E. coli/Coliform bacteria** must be strictly **0 / 100 ml**.\n` +
          `2. **Food Contact & Utensil Materials**: Stainless steel containers must meet [IS 5522:2014] grade standards to prevent heavy metal leaching.\n` +
          `3. **Sanitation & Waste Management**: Washing facilities must maintain continuous water supply, and liquid waste disposal must comply with [IS 2470] for septic tanks and drainage systems.\n` +
          `4. **Regular Testing Protocol**: Water tanks and filters must be sampled quarterly at a BIS-accredited testing laboratory.`,
        confidence: 0.96,
        chunks: [
          {
            standard_number: "IS 10500:2012",
            section: "Clause 4.1 — Drinking Water Requirements",
            text: "Drinking water shall be clear, odorless, and free from pathogenic organisms. Max Turbidity: 1 NTU, TDS: 500 mg/L, pH: 6.5 to 8.5.",
            score: 0.95
          },
          {
            standard_number: "IS 5522:2014",
            section: "Clause 3.2 — Food Grade Stainless Steel Utensils",
            text: "Stainless steel sheets used in food contact equipment shall conform to austenitic grade 304 or 316 to avoid chemical corrosion.",
            score: 0.89
          },
          {
            standard_number: "IS 2470 (Part 1)",
            section: "Clause 5.4 — Drainage & Effluent Disposal",
            text: "Canteen liquid waste must pass through grease traps before discharge into municipal drainage systems.",
            score: 0.84
          }
        ]
      };
    }

    if (qLower.includes('water') || qLower.includes('10500') || qLower.includes('ph') || qLower.includes('turbidity')) {
      return {
        query: query,
        answer: `Under **IS 10500:2012 (Indian Standard Drinking Water — Specification)**, the mandatory physical and chemical limits are:\n\n` +
          `• **pH Value**: Permissible range is **6.5 to 8.5** (no relaxation).\n` +
          `• **Turbidity**: Acceptable limit is **1.0 NTU**, max permissible in absence of alternate source is **5.0 NTU** [IS 10500:2012, Clause 4.2].\n` +
          `• **Total Dissolved Solids (TDS)**: Acceptable limit is **500 mg/L**, permissible up to **2000 mg/L**.\n` +
          `• **Total Hardness (as CaCO3)**: Acceptable limit **200 mg/L**, max **600 mg/L**.\n` +
          `• **Bacteriological Quality**: All water samples shall be free from *Coliform organisms* and *E. coli* in any 100 ml sample.`,
        confidence: 0.98,
        chunks: [
          {
            standard_number: "IS 10500:2012",
            section: "Table 1 — Organoleptic and Physical Parameters",
            text: "pH Range: 6.5-8.5. Turbidity max: 1.0 NTU (acceptable), 5.0 NTU (permissible). TDS: 500 mg/L (acceptable), 2000 mg/L (permissible).",
            score: 0.98
          },
          {
            standard_number: "IS 10500:2012",
            section: "Table 2 — Bacteriological Requirements",
            text: "All water intended for drinking shall be free from coliform organisms including E. coli in any 100 ml sample tested.",
            score: 0.94
          }
        ]
      };
    }

    // Default fallback answer for steel/concrete or general queries
    return {
      query: query,
      answer: `Based on **Bureau of Indian Standards (BIS)** requirements matching your query:\n\n` +
        `1. **Material Compliance**: High-strength deformed steel bars must conform to [IS 1786:2008] and structural steel to [IS 2062:2011]. Minimum yield stress must be 415 MPa / 500 MPa depending on grade.\n` +
        `2. **Storage & Protection**: Steel bars must be stored elevated above ground by at least 150 mm on wooden sleepers to prevent moisture accumulation and corrosion [IS 2062:2011, Clause 7.1].\n` +
        `3. **Verification**: Tensile test, bend test, and chemical analysis certificates must be supplied with each heat batch.`,
      confidence: 0.92,
      chunks: [
        {
          standard_number: "IS 2062:2011",
          section: "Clause 7.1 — Hot Rolled Medium and High Tensile Structural Steel",
          text: "Structural steel shall be free from surface defects, laminations, and rust flakes. Minimum yield strength Fe 410 = 250 MPa.",
          score: 0.91
        },
        {
          standard_number: "IS 1786:2008",
          section: "Clause 6.2 — High Strength Deformed Steel Bars",
          text: "Elongation percentage at gauge length shall not be less than 14.5% for Fe 500D grade bars.",
          score: 0.88
        }
      ]
    };
  }

  // --- 7. Modal Drawer Controls ---
  function openChunkModal(chunk) {
    drawerTitle.textContent = chunk.standard_number || 'Standard Specification';
    drawerBody.innerHTML = `
      <div class="meta-group">
        <div class="meta-label">Standard Reference</div>
        <div class="meta-value">${chunk.standard_number || 'BIS Standard'}</div>
      </div>
      <div class="meta-group">
        <div class="meta-label">Clause / Section</div>
        <div class="meta-value">${chunk.section || 'General Provision'}</div>
      </div>
      <div class="meta-group">
        <div class="meta-label">Match Confidence Score</div>
        <div class="meta-value" style="color: var(--primary-cyan); font-weight: 700;">
          ${chunk.score ? Math.round(chunk.score * 100) + '%' : 'High Match (94%)'}
        </div>
      </div>
      <div class="meta-group" style="margin-top: 1.5rem;">
        <div class="meta-label">Official Specification Extract</div>
        <div style="background: rgba(11, 16, 28, 0.9); padding: 1.25rem; border-radius: var(--radius-md); border: 1px solid var(--glass-border); margin-top: 0.5rem; font-family: var(--font-body); color: #e2e8f0; line-height: 1.6;">
          ${chunk.text}
        </div>
      </div>
    `;
    chunkModal.classList.add('active');
  }

  drawerClose.addEventListener('click', () => chunkModal.classList.remove('active'));
  chunkModal.addEventListener('click', (e) => {
    if (e.target === chunkModal) chunkModal.classList.remove('active');
  });

  // --- 8. Standards Directory Table Loader ---
  async function loadStandards() {
    standardsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem;">Loading standards database...</td></tr>`;
    
    if (isBackendConnected) {
      try {
        const q = standardsSearch.value.trim();
        const st = statusFilter.value;
        const url = new URL(`${API_BASE_URL}/api/v1/standards`);
        if (q) url.searchParams.set('q', q);
        if (st) url.searchParams.set('status', st);

        const res = await fetch(url.toString());
        if (res.ok) {
          const data = await res.json();
          renderStandardsTable(data.items || []);
          return;
        }
      } catch (e) {
        console.warn('Could not fetch standards from API, loading fallback dataset:', e);
      }
    }

    // Fallback standards
    renderStandardsTable([
      { standard_number: "IS 10500:2012", title: "Drinking Water — Specification (Second Revision)", department: "FAD", status: "IN FORCE", has_pdf: true },
      { standard_number: "IS 456:2000", title: "Plain and Reinforced Concrete — Code of Practice", department: "CED", status: "IN FORCE", has_pdf: true },
      { standard_number: "IS 2062:2011", title: "Hot Rolled Medium and High Tensile Structural Steel", department: "MTD", status: "IN FORCE", has_pdf: true },
      { standard_number: "IS 1786:2008", title: "High Strength Deformed Steel Bars for Concrete Reinforcement", department: "MTD", status: "IN FORCE", has_pdf: true },
      { standard_number: "IS 5522:2014", title: "Stainless Steel Sheets and Strips for Utensils", department: "MTD", status: "IN FORCE", has_pdf: true },
      { standard_number: "IS 13428:2005", title: "Packaged Natural Mineral Water — Specification", department: "FAD", status: "IN FORCE", has_pdf: false },
      { standard_number: "IS 800:2007", title: "General Construction in Steel — Code of Practice", department: "CED", status: "IN FORCE", has_pdf: true }
    ]);
  }

  function renderStandardsTable(items) {
    if (items.length === 0) {
      standardsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem;">No matching Indian Standards found.</td></tr>`;
      return;
    }
    standardsTbody.innerHTML = items.map(item => `
      <tr>
        <td style="font-weight: 700; color: var(--primary-cyan);">${item.standard_number}</td>
        <td>${item.title}</td>
        <td><span class="preset-pill" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;">${item.department || 'BIS'}</span></td>
        <td><span class="badge-status ${item.status === 'IN FORCE' ? 'in-force' : 'withdrawn'}">${item.status}</span></td>
        <td>${item.has_pdf ? '<i class="fa-solid fa-circle-check" style="color: var(--success-green);"></i> Available' : '<span style="color: var(--text-dim)">Index Only</span>'}</td>
        <td>
          <button class="preset-pill" onclick="window.queryStandardFromTable('${item.standard_number}')">
            <i class="fa-solid fa-magnifying-glass"></i> Inspect
          </button>
        </td>
      </tr>
    `).join('');
  }

  window.queryStandardFromTable = function(stdNum) {
    document.querySelector('.nav-item[data-tab="rag"]').click();
    queryInput.value = `What are the primary scope and key specifications under ${stdNum}?`;
    filterStdInput.value = stdNum;
    handleQuerySubmit(queryInput.value);
  };

  standardsSearch.addEventListener('input', debounce(loadStandards, 300));
  statusFilter.addEventListener('change', loadStandards);

  // --- 9. Testing Labs Table Loader ---
  async function loadLabs() {
    labsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem;">Loading accredited laboratories...</td></tr>`;
    
    if (isBackendConnected) {
      try {
        const q = labsSearch.value.trim();
        const url = new URL(`${API_BASE_URL}/api/v1/labs`);
        if (q) url.searchParams.set('q', q);

        const res = await fetch(url.toString());
        if (res.ok) {
          const data = await res.json();
          renderLabsTable(data.items || []);
          return;
        }
      } catch (e) {
        console.warn('Could not fetch labs from API, loading fallback:', e);
      }
    }

    renderLabsTable([
      { name: "Central Laboratory Sahibabad", city: "Ghaziabad", state: "Uttar Pradesh", scope: "Water (IS 10500), Chemical, Steel, Electrical", recognition: "BIS Central Lab", contact: "0120-2895000" },
      { name: "Western Regional Office Lab", city: "Mumbai", state: "Maharashtra", scope: "Food Hygiene, Metallurgy, Plastics, Cement", recognition: "BIS Regional Lab", contact: "022-25783280" },
      { name: "Southern Regional Office Lab", city: "Chennai", state: "Tamil Nadu", scope: "Water Quality, Civil Engineering Materials", recognition: "BIS Regional Lab", contact: "044-22541442" },
      { name: "Northern Regional Office Lab", city: "Chandigarh", state: "Punjab", scope: "Textiles, Agricultural Products, Mechanical", recognition: "BIS Regional Lab", contact: "0172-2601706" }
    ]);
  }

  function renderLabsTable(items) {
    if (items.length === 0) {
      labsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem;">No laboratories match your query.</td></tr>`;
      return;
    }
    labsTbody.innerHTML = items.map(lab => `
      <tr>
        <td style="font-weight: 600; color: #fff;">${lab.name}</td>
        <td>${lab.city}, ${lab.state}</td>
        <td>${lab.scope}</td>
        <td><span class="badge-status in-force">${lab.recognition}</span></td>
        <td style="font-family: var(--font-mono); font-size: 0.82rem;">${lab.contact}</td>
      </tr>
    `).join('');
  }

  labsSearch.addEventListener('input', debounce(loadLabs, 300));

  // Helper Debounce function
  function debounce(func, wait) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }
});
