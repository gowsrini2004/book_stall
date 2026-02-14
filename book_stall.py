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
    mapping = mapping or {}
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
    
    # --- Integration: HTML Search Component ---
    import streamlit.components.v1 as components

    # Sync with URL query params
    q_params = st.query_params
    url_q = q_params.get("q", "")
    url_mode = q_params.get("m", "")  # 'all' or 'single'

    # Prepare data for JS search
    search_json = df[["BK_Number", "BK_name", "_search"]].to_json(orient="records")

    html_code = f"""
    <style>
        body {{
            background: transparent;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 0;
            overflow: visible;
        }}
        #search-container {{
            position: relative;
            width: 100%;
            height: 100%;
            z-index: 9999;
        }}
        .search-wrapper {{
            position: relative;
            z-index: 10001;
        }}
        #search-input {{
            width: 100%;
            padding: 14px 18px;
            font-size: 1.15rem;
            background: rgba(40, 44, 52, 0.9);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            color: white;
            outline: none;
            box-sizing: border-box;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}
        #search-input:focus {{
            border-color: #00c2ff;
            background: rgba(40, 44, 52, 0.98);
            box-shadow: 0 0 15px rgba(0, 194, 255, 0.3);
        }}
        #dropdown {{
            position: absolute;
            top: 62px;
            left: 0;
            right: 0;
            background: rgba(30, 34, 42, 0.95);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.6);
            display: none;
            max-height: 280px;
            overflow-y: auto;
            z-index: 10002;
            padding: 6px 0;
        }}
        /* Tooltip-like arrow */
        #dropdown::before {{
            content: '';
            position: absolute;
            top: -6px;
            left: 24px;
            width: 12px;
            height: 12px;
            background: rgba(30, 34, 42, 0.95);
            border-left: 1px solid rgba(255, 255, 255, 0.1);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            transform: rotate(45deg);
        }}
        .item {{
            padding: 12px 18px;
            cursor: pointer;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 1rem;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .item:last-child {{ border-bottom: none; }}
        .item:hover {{
            background: rgba(255, 255, 255, 0.1);
            padding-left: 22px;
        }}
        .item.all {{
            color: #00c2ff;
            font-weight: 700;
            background: rgba(0, 194, 255, 0.08);
            border-bottom: 2px solid rgba(0, 194, 255, 0.2);
        }}
        .info-box {{
            margin-top: 20px;
            padding: 18px;
            background: rgba(0, 194, 255, 0.04);
            border: 1px solid rgba(0, 194, 255, 0.12);
            border-radius: 16px;
            font-size: 0.95rem;
            color: rgba(255, 255, 255, 0.85);
            line-height: 1.6;
            animation: fadeIn 0.5s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(5px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 10px; }}
    </style>

    <div id="search-container">
        <div class="search-wrapper">
            <input type="text" id="search-input" placeholder="Start Typing to Search..." autocomplete="off">
            <div id="dropdown"></div>
        </div>
        <div id="info" class="info-box">
            💡 <b>Welcome to RACK Search!</b><br>
            Quickly find books by typing their <b>Tag #</b>, <b>Name</b>, or <b>Price</b>.
        </div>
    </div>

    <script>
        const data = {search_json};
        const input = document.getElementById('search-input');
        const dropdown = document.getElementById('dropdown');
        const info = document.getElementById('info');

        // Initial sync
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (urlParams.has('q') && urlParams.get('q')) {{
            input.value = urlParams.get('q');
            info.style.display = 'none';
        }}

        input.oninput = (e) => {{
            const val = e.target.value.trim().toLowerCase();
            const originalVal = e.target.value.trim();
            
            if (!val) {{
                dropdown.style.display = 'none';
                info.style.display = 'block';
                return;
            }}
            
            info.style.display = 'none';
            const matches = data.filter(item => item._search.includes(val)).slice(0, 7);
            
            let html = '<div class="item all" data-val="' + originalVal + '" data-mode="all">🔍 Show all matching "' + originalVal + '"</div>';
            matches.forEach(m => {{
                html += '<div class="item" data-val="' + m.BK_Number + '" data-mode="single">📖 ' + m.BK_name + ' (#' + m.BK_Number + ')</div>';
            }});
            
            dropdown.innerHTML = html;
            dropdown.style.display = 'block';

            // Click handling
            document.querySelectorAll('.item').forEach(el => {{
                el.onclick = () => {{
                    selectItem(el.getAttribute('data-val'), el.getAttribute('data-mode'));
                }};
            }});
        }};

        function selectItem(val, mode) {{
            const url = new URL(window.parent.location.href);
            url.searchParams.set("q", val);
            url.searchParams.set("m", mode);
            window.parent.location.href = url.href;
        }}
        
        window.onclick = (e) => {{
            if (!e.target.matches('#search-input')) {{
                dropdown.style.display = 'none';
            }}
        }};
    </script>
    """
    
    st.markdown("### 🔎 Search Books")
    components.html(html_code, height=350)

    # --- Filtering logic ---
    query = url_q
    mode = url_mode

    if not query:
        st.stop()

    def smart_filter_new(data_in: pd.DataFrame, q: str, m: str) -> pd.DataFrame:
        if not q or not q.strip():
            return data_in.iloc[0:0]
        
        if m == "single":
            return data_in[data_in["BK_Number"].astype(str) == str(q)]
        
        qn = " ".join(q.lower().strip().split())
        return data_in[data_in["_search"].str.contains(qn, na=False)]

    all_results = smart_filter_new(df, query, mode)
    total_found = len(all_results)
    
    if "num_results" not in st.session_state:
        st.session_state.num_results = 50
    
    results = all_results.head(st.session_state.num_results)

    if query.strip():
        st.markdown(f"**Results:** {len(results)} of {total_found}")

    # --- Mobile cards ---
    if total_found == 0:
        st.warning(f"No matches found for '{query}'.")
    else:
        for _, r in results.iterrows():
            st.markdown(
                f"""
                <div class="result-card">
                  <div class="rowline">
                    <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <div class="tag-badge">#{r['BK_Number']}</div>
                        <div class="rate-badge">₹ {r['BK_rate']}</div>
                        <div class="rack-badge">📍 {r['BK_row']}</div>
                    </div>
                  </div>
                  <div style="margin-top:16px; font-size:1.4rem; font-weight: 700; line-height: 1.3;">{r['BK_name']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if total_found > st.session_state.num_results:
            if st.button("🔽 Show More", use_container_width=True):
                st.session_state.num_results += 50
                st.rerun()

        if total_found == 1:
            one = results.iloc[0]
            st.success(f"✅ Location: **{one['BK_row']}**  |  Rate: **₹ {one['BK_rate']}**")
