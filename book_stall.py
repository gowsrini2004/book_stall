import streamlit as st
import pandas as pd
import re
import json
from pathlib import Path

st.set_page_config(page_title="BK Search Pro", layout="centered")  # better for phone

CONFIG_PATH = Path("config.json")
ADMIN_PASSWORD = "mother"

APP_FIELDS = ["BK_Number", "BK_name", "BK_rate", "BK_row", "BK_image"]  # standard names inside the app


# ---------------------------
# Config helpers
# ---------------------------
def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

import requests
import io

def extract_sheet_id(url: str | None):
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url or "")
    return match.group(1) if match else None
 
def fix_drive_url(url: str) -> str:
    """Converts a Google Drive sharing link to a direct image download link."""
    if not isinstance(url, str) or "drive.google.com" not in url:
        return url
    
    # Extract file ID
    file_id = ""
    # Standard format: /file/d/ID/view
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
    # Query param format: id=ID
    elif "id=" in url:
        # Avoid picking up other params like 'id=123&usp=sharing'
        parts = url.split("id=")[1].split("&")
        file_id = parts[0]
    # Simple 'open' format: open?id=ID
    elif "open?" in url and "id=" in url:
        file_id = url.split("id=")[1].split("&")[0]
    
    if file_id:
        # The 'thumbnail' endpoint is often more reliable for displaying public Drive images
        # sz=w1000 provides a high-res thumbnail suitable for a modal
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
    return url


# ---------------------------
# Google Sheet loader
# ---------------------------
@st.cache_data(ttl=3600)  # Cache for 1 hour to avoid constant re-fetching
def fetch_sheet_df(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    try:
        # Use requests with a timeout to prevent the app from hanging on a slow connection
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        raise Exception(f"Failed to fetch data: {str(e)}")

def apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    # BK_image is optional
    required_fields = ["BK_Number", "BK_name", "BK_rate", "BK_row"]
    missing = [k for k in required_fields if k not in mapping or not mapping[k]]
    if missing:
        raise ValueError(f"Mapping not set for mandatory fields: {missing}")

    for app_col, sheet_col in mapping.items():
        if sheet_col not in df.columns:
            raise ValueError(f"Mapped column '{sheet_col}' not found. Found: {df.columns.tolist()}")

    # Rename only columns that are mapped
    rename_map = {mapping[k]: k for k in APP_FIELDS if k in mapping and mapping[k]}
    df2 = df.rename(columns=rename_map)

    # Clean + normalize search fields (excluding BK_image from search blob)
    for c in APP_FIELDS:
        if c in df2.columns:
            if c == "BK_image":
                df2[c] = df2[c].astype(str).replace(["nan", "None", "<NA>"], "").str.strip().apply(fix_drive_url)
            else:
                df2[c] = df2[c].astype(str).replace(["nan", "None", "<NA>"], "").str.strip()
        else:
            df2[c] = ""

    # Create a single search blob (number + name + rate + row)
    df2["_search"] = (
        df2["BK_Number"].astype(str) + " " +
        df2["BK_name"].astype(str) + " " +
        df2["BK_rate"].astype(str) + " " +
        df2["BK_row"].astype(str)
    ).str.lower()

    return df2


# ---------------------------
# Session state
# ---------------------------
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "show_admin_login" not in st.session_state:
    st.session_state.show_admin_login = False

cfg = load_config()
cfg.setdefault("sheet_url", "")
cfg.setdefault("sheet_name", "Sheet1")
cfg.setdefault("mapping", {})


# ---------------------------
# Small header (phone friendly)
# ---------------------------
st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem; padding-bottom: 1rem; }
      .big-search input { font-size: 1.15rem !important; padding: 0.85rem !important; }
      .result-card {
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 14px 14px;
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
      }
      .rack-badge {
        display:inline-block;
        padding: 10px 14px;
        border-radius: 14px;
        font-weight: 800;
        font-size: 1.1rem;
        background: #00c2ff22;
        border: 1px solid #00c2ff55;
      }
      .rate-badge {
        display:inline-block;
        padding: 10px 14px;
        border-radius: 14px;
        font-weight: 600;
        font-size: 1.1rem;
        background: #00c2ff08;
        border: 1px solid #00c2ff22;
        color: #00c2ff;
      }
      .tag-badge {
        display:inline-block;
        padding: 10px 14px;
        border-radius: 14px;
        font-weight: 800;
        font-size: 1.1rem;
        background: #ffc10722;
        border: 1px solid #ffc10755;
        color: #ffc107;
      }
      .muted { opacity: 0.8; font-size: 0.95rem; }
      .tiny { opacity: 0.75; font-size: 0.85rem; }
      .rowline { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
      .btn-row { display:flex; justify-content:flex-end; }
      
      /* Target the logout button specifically if it's the secondary type */
      div[data-testid="stButton"] button:hover {
          border-color: #ff4b4b22 !important;
          background-color: #ff4b4b11 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

#for repush
# ---------------------------
# Compact Header (Admin small button)
# ---------------------------

# ---------------------------
# Compact Header (Navigation & Admin)
# ---------------------------
h_left, h_right = st.columns([8, 2])

with h_left:
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("## 📚 RACK Search")

with h_right:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if not st.session_state.is_admin:
        # Normal sized gear button
        if st.button("⚙️", key="admin_btn"):
            st.session_state.show_admin_login = True
            st.rerun()
    else:
        # Wide Logout button with icon + text
        if st.button("🚪 Logout", key="logout_btn", use_container_width=True, type="secondary"):
            st.session_state.is_admin = False
            st.session_state.show_admin_login = False
            st.rerun()


# ---------------------------
# Admin login
# ---------------------------
if st.session_state.show_admin_login and not st.session_state.is_admin:
    with st.container(border=True):
        st.subheader("Admin Login")
        pwd = st.text_input("Password", type="password", placeholder="password")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Login", type="primary"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.is_admin = True
                    st.session_state.show_admin_login = False
                    st.success("✅ Admin access granted")
                    st.rerun()
                else:
                    st.error("❌ Wrong password")
        with c2:
            if st.button("Cancel"):
                st.session_state.show_admin_login = False
                st.rerun()


# ---------------------------
# GLOBAL SEARCH RENDERER
# ---------------------------
def render_search_interface(df: pd.DataFrame):
    if df is None:
        st.error("Sheet not available for search.")
        return

    # --- Integration: Consolidated HTML Search & Results Component ---
    import streamlit.components.v1 as components

    search_json = df[APP_FIELDS + ["_search"]].to_json(orient="records")

    # We use a regular string and then replace {{search_json}} to avoid f-string SyntaxErrors
    html_code = r'''
    <style>
        body {
            background: transparent;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 0;
        }
        #search-container {
            position: sticky;
            top: 0;
            background: #0e1117; /* Same as streamlit dark theme */
            padding: 10px 0;
            z-index: 1000;
            margin-bottom: 10px;
        }
        #search-input {
            width: 100%;
            padding: 14px 16px;
            padding-right: 50px;
            font-size: 1.15rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            color: white;
            outline: none;
            box-sizing: border-box;
            transition: all 0.2s;
        }
        #search-input:focus {
            border-color: #00c2ff;
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 12px rgba(0, 194, 255, 0.2);
        }
        #dropdown {
            position: absolute;
            top: 60px;
            left: 0;
            right: 0;
            background: #1e1e1e;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.6);
            display: none;
            max-height: 350px;
            overflow-y: auto;
            z-index: 2000;
        }
        .dropdown-item {
            padding: 14px 16px;
            cursor: pointer;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 1.05rem;
            transition: background 0.2s;
            display: flex;
            align-items: center;
        }
        .dropdown-item:last-child { border-bottom: none; }
        .dropdown-item:hover {
            background: rgba(255, 255, 255, 0.08);
        }
        .dropdown-item.all-btn {
            color: #00c2ff;
            font-weight: 700;
            background: rgba(0, 194, 255, 0.05);
        }

        #search-btn {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            background: #00c2ff;
            border: none;
            border-radius: 8px;
            color: white;
            width: 36px;
            height: 36px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        #search-btn:hover { background: #00ace6; }

        #clear-btn {
            position: absolute;
            right: 52px;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 50%;
            color: #aaa;
            width: 24px;
            height: 24px;
            cursor: pointer;
            display: none;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            transition: all 0.2s;
        }
        #clear-btn:hover { background: rgba(255, 255, 255, 0.2); color: white; }

        #results-area {
            margin-top: 5px;
            height: 650px; /* Fixed height for internal scrolling */
            overflow-y: auto;
            padding: 0 10px 100px 10px; /* Equal padding on both sides */
            scrollbar-gutter: stable; /* Reserves space so content doesn't jump */
        }
        /* Sleek scrollbar for results */
        #results-area::-webkit-scrollbar { width: 6px; }
        #results-area::-webkit-scrollbar-thumb { background: rgba(0, 194, 255, 0.4); border-radius: 10px; }
        #results-area::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); border-radius: 10px; }
        .result-card {
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 20px;
            padding: 24px 22px; /* Increased vertical padding */
            margin-bottom: 25px; /* More space between cards */
            background: rgba(255,255,255,0.03);
            animation: fadeIn 0.3s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .badge-row {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-bottom: 22px; /* More gap between top and bottom info */
        }
        .name-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
        }
        .placeholder-badge {
            background: transparent !important;
            border: none !important;
            height: 34px;
        }
        .tag-badge, .rate-badge, .rack-badge, .img-btn {
            padding: 6px 8px; /* Slightly tighter horizontal padding */
            border-radius: 10px;
            font-weight: 800;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            min-height: 34px;
            box-sizing: border-box;
            white-space: nowrap; /* Prevent 2 lines */
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .tag-badge {
            background: rgba(255, 193, 7, 0.15);
            border: 1px solid rgba(255, 193, 7, 0.3);
            color: #ffc107;
        }
        .rate-badge {
            background: rgba(0, 194, 255, 0.05);
            border: 1px solid rgba(0, 194, 255, 0.15);
            color: #00c2ff;
        }
        .rack-badge {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: #ffffff;
        }
        .img-btn {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: #ffffff;
            cursor: pointer;
            transition: all 0.2s;
        }
        .img-btn:hover {
            background: rgba(0, 194, 255, 0.2);
            border-color: #00c2ff;
        }
        .sm-icon { width: 40px; flex-shrink: 0; }
        .img-btn:hover {
            background: rgba(0, 194, 255, 0.2);
            border-color: #00c2ff;
            transform: scale(1.05);
        }
        
        /* Modal - Professional Popup */
        #modal-overlay {
            position: absolute; /* Relative to the search component */
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.6); /* Re-adding a bit of contrast for mobile visibility */
            backdrop-filter: blur(4px);
            display: none;
            justify-content: center;
            align-items: flex-start; /* Ensure it shows at the top */
            z-index: 9999;
            padding: 10px;
            padding-top: 40px; /* Offset from the top of the view */
            box-sizing: border-box;
        }
        #modal-content {
            background: #1a1a1a;
            border: 2px solid rgba(0, 194, 255, 0.4);
            border-radius: 20px;
            max-width: 95%; /* Better for phones */
            width: 450px;
            position: relative;
            padding: 20px;
            box-shadow: 0 10px 50px rgba(0,0,0,0.8);
            animation: modalIn 0.3s ease-out;
        }
        @keyframes modalIn {
            from { opacity: 0; transform: scale(0.9) translateY(20px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
        }
        #modal-close {
            position: absolute;
            top: 15px;
            right: 15px;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 50%;
            width: 32px;
            height: 32px;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            transition: all 0.2s;
            z-index: 10;
        }
        #modal-close:hover { background: #ff4b4b; }
        
        .modal-img-container {
            width: 100%;
            border-radius: 16px;
            overflow: hidden;
            margin-top: 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255,255,255,0.08);
            min-height: 250px;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }
        .modal-img {
            width: 100%;
            height: auto;
            max-height: 500px;
            display: block;
            object-fit: contain;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .modal-title { font-size: 1.3rem; font-weight: 800; color: #00c2ff; margin-bottom: 20px; padding-right: 40px; }
        .modal-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
        .m-item { background: rgba(255,255,255,0.04); padding: 8px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.06); text-align: center; }
        .m-label { font-size: 0.6rem; color: #aaa; text-transform: uppercase; font-weight: 800; margin-bottom: 2px; }
        .m-val { font-size: 0.85rem; font-weight: 700; color: #fff; }

        .loading-text {
            position: absolute;
            color: #00c2ff;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }

        .book-name {
// ... existing CSS ...
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.4;
            color: #ffffff;
        }
        .info-card {
            background: rgba(0, 194, 255, 0.05);
            border: 1px solid rgba(0, 194, 255, 0.15);
            border-radius: 16px;
            padding: 20px;
            text-align: left;
            margin-top: 10px;
        }
        .info-card h4 { margin-top: 0; color: #00c2ff; font-size: 1.2rem; }
        .info-card p { margin-bottom: 0; opacity: 0.9; line-height: 1.6; }
        
        .no-matches {
            padding: 30px;
            text-align: center;
            opacity: 0.7;
            background: rgba(255,255,255,0.02);
            border-radius: 16px;
            border: 1px dashed rgba(255,255,255,0.1);
        }
        
        .show-more-btn {
            width: 100%;
            padding: 14px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            color: white;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 600;
            margin-top: 10px;
            transition: background 0.2s;
        }
        .show-more-btn:hover { background: rgba(255,255,255,0.1); }
    </style>

    <div id="search-container">
        <div style="position: relative;">
            <input type="text" id="search-input" placeholder="Start Typing to Search..." autocomplete="off">
            <button id="clear-btn" onclick="clearSearch()">✕</button>
            <button id="search-btn" onclick="performSearch(document.getElementById('search-input').value, 'all')">
                <svg style="width:18px; height:18px;" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"></path></svg>
            </button>
        </div>
        <div id="dropdown"></div>
    </div>

    <!-- Details Modal -->
    <div id="modal-overlay" onclick="closeModal(event)">
        <div id="modal-content" onclick="event.stopPropagation()">
            <button id="modal-close" onclick="closeModal()">✕</button>
            <div id="modal-body"></div>
        </div>
    </div>

    <div id="results-area">
        <div class="info-card">
            <h4>💡 Welcome to RACK Search!</h4>
            <p>Simply start typing in the box above to find books by <b>BK Number</b>, <b>Book Name</b>, <b>Rack Location</b>, or even <b>Book Price</b>.</p>
        </div>
    </div>

    <script>
        const allData = {{search_json}};
        const input = document.getElementById('search-input');
        const clearBtn = document.getElementById('clear-btn');
        const dropdown = document.getElementById('dropdown');
        const resultsArea = document.getElementById('results-area');
        const modalOverlay = document.getElementById('modal-overlay');
        const modalBody = document.getElementById('modal-body');

        window.clearSearch = () => {
            input.value = '';
            clearBtn.style.display = 'none';
            dropdown.style.display = 'none';
            performSearch('', 'all');
            input.focus();
        };
        
        let currentResults = [];
        let displayLimit = 50;

        function fixDriveUrl(url) {
            if (!url || !url.includes('drive.google.com')) return url;
            let fileId = '';
            if (url.includes('/file/d/')) {
                fileId = url.split('/file/d/')[1].split('/')[0];
            } else if (url.includes('id=')) {
                fileId = url.split('id=')[1].split('&')[0];
            }
            // Use same thumbnail logic in JS for immediate fallback
            return fileId ? `https://drive.google.com/thumbnail?id=${fileId}&sz=w1000` : url;
        }

        function showDetails(index) {
            const r = currentResults[index];
            if (!r) return;
            
            const finalImg = fixDriveUrl(r.BK_image || '');
            
            // Auto-scroll to top of search component so modal is visible
            window.scrollTo({ top: 0, behavior: 'smooth' });
            
            const rateHtml = (r.BK_rate && r.BK_rate.trim() !== "") ? 
                `<div class="m-item"><div class="m-label">Price</div><div class="m-val">₹ ${r.BK_rate}</div></div>` : "";
            
            modalBody.innerHTML = `
                <div class="modal-title">${r.BK_name}</div>
                <div class="modal-grid" style="grid-template-columns: repeat(${rateHtml ? 3 : 2}, 1fr);">
                    <div class="m-item"><div class="m-label">Book Code</div><div class="m-val">#${r.BK_Number}</div></div>
                    ${rateHtml}
                    <div class="m-item"><div class="m-label">Rack Location</div><div class="m-val">📍 ${r.BK_row}</div></div>
                </div>
                <div class="modal-img-container">
                    <div id="img-loader" class="loading-text">
                        <svg class="animate-spin" style="width:20px; height:20px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="10" opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path></svg>
                        Loading Image...
                    </div>
                    <img class="modal-img" src="${finalImg}" 
                         onload="this.style.opacity=1; document.getElementById('img-loader').style.display='none';" 
                         onerror="this.style.display='none'; document.getElementById('img-loader').innerHTML='❌ Load Failed';">
                </div>
            `;
            modalOverlay.style.display = 'flex';
        }

        window.closeModal = (e) => {
            modalOverlay.style.display = 'none';
        }

        function renderCards() {
            if (currentResults.length === 0) {
                resultsArea.innerHTML = '<div class="no-matches">No matches found.</div>';
                return;
            }
            
            let html = '';
            const toShow = currentResults.slice(0, displayLimit);
            
            toShow.forEach((r, idx) => {
                const hasImage = r.BK_image && r.BK_image.trim().length > 5;
                const hasRate = r.BK_rate && r.BK_rate.trim() !== "";
                const hasRack = r.BK_row && r.BK_row.trim() !== "";
                
                // Slot 1: BK Number (Always present)
                const slot1 = `<div class="tag-badge"># ${r.BK_Number}</div>`;
                
                // Slot 2: Rate (Or placeholder)
                const slot2 = hasRate ? `<div class="rate-badge">₹${r.BK_rate}</div>` : `<div class="placeholder-badge"></div>`;
                
                // Slot 3: Rack (Or placeholder)
                const slot3 = hasRack ? `<div class="rack-badge">📍${r.BK_row}</div>` : `<div class="placeholder-badge"></div>`;
                
                // Slot 5: Image Icon (Next to name)
                const slot5 = hasImage ? `<div class="img-btn sm-icon" onclick="showDetails(${idx})">📷</div>` : `<div style="width:40px;"></div>`;

                html += `
                <div class="result-card">
                    <div class="badge-row">
                        ${slot1}
                        ${slot2}
                        ${slot3}
                    </div>
                    <div class="name-row">
                        <div class="book-name">${r.BK_name}</div>
                        ${slot5}
                    </div>
                </div>
                `;
            });
            
            if (currentResults.length > displayLimit) {
                html += `<button class="show-more-btn" onclick="increaseLimit()">🔽 Show More Results</button>`;
            }
            
            resultsArea.innerHTML = html;
        }

        window.increaseLimit = () => {
            displayLimit += 50;
            renderCards();
        };

        function performSearch(query, mode, exactId = null) {
            displayLimit = 50;
            dropdown.style.display = 'none';
            
            if (!query.trim()) {
                currentResults = [];
                resultsArea.innerHTML = `
                    <div class="info-card">
                        <h4>💡 Welcome to RACK Search!</h4>
                        <p>Simply start typing in the box above to find books by <b>BK Number</b>, <b>Book Name</b>, <b>Rack Location</b>, or even <b>Book Price</b>.</p>
                    </div>
                `;
                return;
            }

            if (mode === 'single' && exactId) {
                currentResults = allData.filter(item => String(item.BK_Number) === String(exactId));
                input.value = currentResults[0]?.BK_name || query;
            } else {
                const qn = query.toLowerCase().trim();
                currentResults = allData.filter(item => item._search.includes(qn));
            }
            
            renderCards();
        }

        input.oninput = (e) => {
            const val = e.target.value.trim().toLowerCase();
            const originalVal = e.target.value;
            
            clearBtn.style.display = originalVal ? 'flex' : 'none';
            
            if (!val) {
                dropdown.style.display = 'none';
                performSearch('', 'all');
                return;
            }
            
            const matches = allData.filter(item => item._search.includes(val)).slice(0, 7);
            
            let html = `<div class="dropdown-item all-btn" onclick="performSearch('${originalVal.replace(/'/g, "\\'")}', 'all')">
                <svg style="width:18px; height:18px; margin-right:12px; opacity:0.8;" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                Show all matching "${originalVal}"
            </div>`;
            matches.forEach(m => {
                html += `<div class="dropdown-item" onclick="performSearch('${m.BK_name.replace(/'/g, "\\'")}', 'single', '${m.BK_Number}')">
                    <svg style="width:18px; height:18px; margin-right:12px; opacity:0.6;" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.168.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
                    ${m.BK_name} (#${m.BK_Number})
                </div>`;
            });
            
            dropdown.innerHTML = html;
            dropdown.style.display = 'block';
        };

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#search-container')) {
                dropdown.style.display = 'none';
            }
        });

        // Enter key support
        input.onkeypress = (e) => {
            if (e.key === 'Enter') {
                performSearch(input.value, 'all');
            }
        };
    </script>
    '''.replace("{{search_json}}", search_json)

    st.markdown("### 🔎 Search Books")
    # 850px is a perfect height for most mobile/desktop views without clipping
    components.html(html_code, height=850, scrolling=False)

# ---------------------------
# Load sheet (if configured)
# ---------------------------
df_raw, load_error = None, None
s_id = extract_sheet_id(cfg.get("sheet_url", ""))
s_name = cfg.get("sheet_name", "Sheet1")

if s_id and s_name:
    try:
        df_raw = fetch_sheet_df(s_id, s_name)
    except Exception as e:
        load_error = str(e)


# ---------------------------
# ADMIN PANEL
# ---------------------------
if st.session_state.is_admin:
    st.divider()
    st.header("🛠️ Admin Panel")

    tabs = st.tabs([" Setup & Mapping", "📄 View Data", "🔎 Search Book"])

    with tabs[0]:
        st.subheader("Dynamic Column Mapping")
        
        # Refresh button to bypass 1-hour cache
        if st.button("🔄 Refresh Sheet Data", use_container_width=True):
            st.cache_data.clear()
            st.success("Refreshed! Loading latest data...")
            st.rerun()

        st.caption(f"Connected to Sheet: {s_name}")

        if load_error:
            st.error(f"Could not load sheet: {load_error}")
        else:
            st.success("✅ Sheet columns detected")
            sheet_cols = df_raw.columns.tolist()

            st.markdown("### Map Columns")
            st.caption("Pick which sheet columns match the app fields.")

            current = cfg.get("mapping", {})
            options = [""] + sheet_cols

            new_mapping = {}
            new_mapping["BK_Number"] = st.selectbox(
                "App field: BK_Number (Book Number)",
                options=options,
                index=options.index(current.get("BK_Number", "")) if current.get("BK_Number", "") in options else 0,
            )
            new_mapping["BK_name"] = st.selectbox(
                "App field: BK_name (Book Name)",
                options=options,
                index=options.index(current.get("BK_name", "")) if current.get("BK_name", "") in options else 0,
            )
            new_mapping["BK_rate"] = st.selectbox(
                "App field: BK_rate (Book Rate / Price)",
                options=options,
                index=options.index(current.get("BK_rate", "")) if current.get("BK_rate", "") in options else 0,
            )
            new_mapping["BK_row"] = st.selectbox(
                "App field: BK_row (Rack / Row / Location)",
                options=options,
                index=options.index(current.get("BK_row", "")) if current.get("BK_row", "") in options else 0,
            )
            new_mapping["BK_image"] = st.selectbox(
                "App field: BK_image (Image URL) [Optional]",
                options=options,
                index=options.index(current.get("BK_image", "")) if current.get("BK_image", "") in options else 0,
            )

            chosen = [v for v in new_mapping.values() if v]
            dupes = {x for x in chosen if chosen.count(x) > 1}
            if dupes:
                st.warning(f"Same sheet column selected multiple times: {sorted(list(dupes))}")

            st.caption("Preview:")
            try:
                mapped_preview = apply_mapping(df_raw, new_mapping)
                st.dataframe(mapped_preview[APP_FIELDS], width="stretch", height=250)
            except Exception as e:
                st.info(f"Preview not ready: {e}")

            if st.button("💾 Save Configuration", type="primary"):
                cfg["mapping"] = new_mapping
                save_config(cfg)
                st.cache_data.clear()
                st.success("✅ Saved locally!")
                st.rerun()

    with tabs[1]:
        st.subheader("View Sheet Data")

        if not cfg.get("sheet_url") or not cfg.get("sheet_name"):
            st.info("Go to Setup & Mapping tab and configure the sheet.")
        elif load_error:
            st.error(f"Could not load sheet: {load_error}")
            st.info("Share sheet as: Anyone with link → Viewer")
        else:
            st.success("✅ Sheet loaded")
            st.dataframe(df_raw, width="stretch", height=420)

            st.caption("Mapped preview (what the app uses):")
            try:
                mapped = apply_mapping(df_raw, cfg.get("mapping", {}))
                st.dataframe(mapped[APP_FIELDS], width="stretch", height=250)
            except Exception as e:
                st.warning(f"Mapping not ready: {e}")

    with tabs[2]:
        if load_error:
            st.error(f"Could not load sheet: {load_error}")
        elif df_raw is None:
            st.error("Sheet not available.")
        else:
            try:
                df = apply_mapping(df_raw, cfg.get("mapping", {}))
                render_search_interface(df)
            except Exception as e:
                st.warning(f"App is not configured properly (mapping issue): {e}")

# ---------------------------
# PUBLIC USER SEARCH
# ---------------------------
if not st.session_state.is_admin:
    st.divider()

    if load_error:
        st.error(f"Could not load sheet: {load_error}")
        st.info("Make sure the Sheet is shared as: Anyone with link → Viewer")
    elif df_raw is None:
        st.error("Sheet not available.")
    else:
        try:
            df = apply_mapping(df_raw, cfg.get("mapping", {}))
            render_search_interface(df)
        except Exception as e:
            st.warning(f"App is not configured properly (mapping issue): {e}")
            st.stop()
    
