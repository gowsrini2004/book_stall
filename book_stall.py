import streamlit as st
import pandas as pd
import re
import json
from pathlib import Path

st.set_page_config(page_title="BK Search Pro", layout="centered")  # better for phone

CONFIG_PATH = Path("config.json")
ADMIN_PASSWORD = "mother"

APP_FIELDS = ["BK_Number", "BK_name", "BK_rate", "BK_row"]  # standard names inside the app


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
    # mapping: { "BK_Number": "BK_No", "BK_name": "BK_Name", "BK_row": "BK_Rack" }
    missing = [k for k in APP_FIELDS if k not in mapping or not mapping[k]]
    if missing:
        raise ValueError(f"Mapping not set for: {missing}")

    for app_col, sheet_col in mapping.items():
        if sheet_col not in df.columns:
            raise ValueError(f"Mapped column '{sheet_col}' not found. Found: {df.columns.tolist()}")

    df2 = df.rename(columns={mapping[k]: k for k in APP_FIELDS})

    # Clean + normalize search fields
    for c in APP_FIELDS:
        df2[c] = df2[c].astype(str).fillna("").str.strip()

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
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Compact Header (Admin small button)
# ---------------------------

header_left, header_right = st.columns([9, 1])

with header_left:
    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)  # more space above header
    st.markdown("## 📚 RACK Search")

with header_right:
    if not st.session_state.is_admin:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)  # more space above header
        st.button("⚙️", key="admin_btn")
    else:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)  # more space above header
        st.button("🚪", key="logout_btn")

# Handle button clicks separately (so layout stays clean)
if not st.session_state.is_admin:
    if st.session_state.get("admin_btn"):
        st.session_state.show_admin_login = True
else:
    if st.session_state.get("logout_btn"):
        st.session_state.is_admin = False
        st.session_state.show_admin_login = False


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

    tabs = st.tabs(["📄 View Data", "🔧 Setup & Mapping"])

    with tabs[0]:
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

    with tabs[1]:
        st.subheader("Dynamic Column Mapping")
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

# ---------------------------
# USER SEARCH (mobile-first)
# ---------------------------
st.divider()

if load_error:
    st.error(f"Could not load sheet: {load_error}")
    st.info("Make sure the Sheet is shared as: Anyone with link → Viewer")
elif df_raw is None:
    st.error("Sheet not available.")
else:
    try:
        df = apply_mapping(df_raw, cfg.get("mapping", {}))
    except Exception as e:
        st.warning(f"App is not configured properly (mapping issue): {e}")
        st.stop()
    
    # --- Integration: Consolidated HTML Search & Results Component ---
    import streamlit.components.v1 as components

    # Prepare data for JS search (ensure columns exist and are clean)
    search_json = df[APP_FIELDS + ["_search"]].to_json(orient="records")

    html_code = f"""
    <style>
        body {{
            background: transparent;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 0;
        }}
        #search-container {{
            position: relative;
            width: 100%;
            margin-bottom: 20px;
        }}
        #search-input {{
            width: 100%;
            padding: 14px 16px;
            font-size: 1.15rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            color: white;
            outline: none;
            box-sizing: border-box;
            transition: all 0.2s;
        }}
        #search-input:focus {{
            border-color: #00c2ff;
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 12px rgba(0, 194, 255, 0.2);
        }}
        #dropdown {{
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
        }}
        .dropdown-item {{
            padding: 14px 16px;
            cursor: pointer;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 1.05rem;
            transition: background 0.2s;
        }}
        .dropdown-item:last-child {{ border-bottom: none; }}
        .dropdown-item:hover {{
            background: rgba(255, 255, 255, 0.08);
        }}
        .dropdown-item.all-btn {{
            color: #00c2ff;
            font-weight: 700;
            background: rgba(0, 194, 255, 0.05);
        }}

        #results-area {{
            margin-top: 10px;
        }}
        .result-card {{
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 15px;
            background: rgba(255,255,255,0.03);
            animation: fadeIn 0.3s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .rowline {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }}
        .badge-group {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .tag-badge {{
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 1rem;
            background: rgba(255, 193, 7, 0.15);
            border: 1px solid rgba(255, 193, 7, 0.3);
            color: #ffc107;
        }}
        .rate-badge {{
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 1rem;
            background: rgba(0, 194, 255, 0.05);
            border: 1px solid rgba(0, 194, 255, 0.15);
            color: #00c2ff;
        }}
        .rack-badge {{
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 1rem;
            background: rgba(0, 194, 255, 0.15);
            border: 1px solid rgba(0, 194, 255, 0.3);
            color: #ffffff;
        }}
        .book-name {{
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.4;
            color: #ffffff;
        }}
        .info-card {{
            background: rgba(0, 194, 255, 0.05);
            border: 1px solid rgba(0, 194, 255, 0.15);
            border-radius: 16px;
            padding: 20px;
            text-align: left;
            margin-top: 10px;
        }}
        .info-card h4 {{ margin-top: 0; color: #00c2ff; font-size: 1.2rem; }}
        .info-card p {{ margin-bottom: 0; opacity: 0.9; line-height: 1.6; }}
        
        .no-matches {{
            padding: 30px;
            text-align: center;
            opacity: 0.7;
            background: rgba(255,255,255,0.02);
            border-radius: 16px;
            border: 1px dashed rgba(255,255,255,0.1);
        }}
        
        .show-more-btn {{
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
        }}
        .show-more-btn:hover {{ background: rgba(255,255,255,0.1); }}
    </style>

    <div id="search-container">
        <input type="text" id="search-input" placeholder="Start Typing to Search..." autocomplete="off">
        <div id="dropdown"></div>
    </div>

    <div id="results-area">
        <div class="info-card">
            <h4>💡 Welcome to RACK Search!</h4>
            <p>Simply start typing in the box above to find books by <b>Tag Number</b>, <b>Name</b>, <b>Rack Location</b>, or even <b>Price</b>.</p>
        </div>
    </div>

    <script>
        const allData = {search_json};
        const input = document.getElementById('search-input');
        const dropdown = document.getElementById('dropdown');
        const resultsArea = document.getElementById('results-area');
        
        let currentResults = [];
        let displayLimit = 50;

        function renderCards() {{
            if (currentResults.length === 0) {{
                resultsArea.innerHTML = '<div class="no-matches">No matches found.</div>';
                return;
            }}
            
            let html = '';
            const toShow = currentResults.slice(0, displayLimit);
            
            toShow.forEach(r => {{
                html += `
                <div class="result-card">
                    <div class="rowline">
                        <div class="badge-group">
                            <div class="tag-badge">#${{r.BK_Number}}</div>
                            <div class="rate-badge">₹ ${{r.BK_rate}}</div>
                            <div class="rack-badge">📍 ${{r.BK_row}}</div>
                        </div>
                    </div>
                    <div class="book-name">${{r.BK_name}}</div>
                </div>
                `;
            }});
            
            if (currentResults.length > displayLimit) {{
                html += `<button class="show-more-btn" onclick="increaseLimit()">🔽 Show More Results</button>`;
            }}
            
            resultsArea.innerHTML = html;
        }}

        window.increaseLimit = () => {{
            displayLimit += 50;
            renderCards();
        }};

        function performSearch(query, mode, exactId = null) {{
            displayLimit = 50;
            dropdown.style.display = 'none';
            
            if (!query.trim()) {{
                currentResults = [];
                resultsArea.innerHTML = `
                    <div class="info-card">
                        <h4>💡 Welcome to RACK Search!</h4>
                        <p>Simply start typing in the box above to find books by <b>Tag Number</b>, <b>Name</b>, <b>Rack Location</b>, or even <b>Price</b>.</p>
                    </div>
                `;
                return;
            }}

            if (mode === 'single' && exactId) {{
                currentResults = allData.filter(item => String(item.BK_Number) === String(exactId));
                input.value = currentResults[0]?.BK_name || query;
            }} else {{
                const qn = query.toLowerCase().trim();
                currentResults = allData.filter(item => item._search.includes(qn));
            }}
            
            renderCards();
        }}

        input.oninput = (e) => {{
            const val = e.target.value.trim().toLowerCase();
            const originalVal = e.target.value;
            
            if (!val) {{
                dropdown.style.display = 'none';
                performSearch('', 'all');
                return;
            }}
            
            const matches = allData.filter(item => item._search.includes(val)).slice(0, 7);
            
            let html = `<div class="dropdown-item all-btn" onclick="performSearch('${{originalVal.replace(/'/g, "\\'")}}', 'all')">🔍 Show all matching "${{originalVal}}"</div>`;
            matches.forEach(m => {{
                html += `<div class="dropdown-item" onclick="performSearch('${{m.BK_name.replace(/'/g, "\\'")}}', 'single', '${{m.BK_Number}}')">� ${{m.BK_name}} (#${{m.BK_Number}})</div>`;
            }});
            
            dropdown.innerHTML = html;
            dropdown.style.display = 'block';
        }};

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {{
            if (!e.target.closest('#search-container')) {{
                dropdown.style.display = 'none';
            }}
        }});

        // Enter key support
        input.onkeypress = (e) => {{
            if (e.key === 'Enter') {{
                performSearch(input.value, 'all');
            }}
        }};
    </script>
    """
    
    st.markdown("### 🔎 Search Books")
    # Set height large enough for results, but disable internal scrollbar for "integrated" feel
    components.html(html_code, height=1800, scrolling=False)
