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

def extract_sheet_id(url: str):
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url or "")
    return match.group(1) if match else None


# ---------------------------
# Google Sheet loader
# ---------------------------
@st.cache_data(ttl=60)
def fetch_sheet_df(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    df = pd.read_csv(url)
    df.columns = [c.strip() for c in df.columns]
    return df

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

    # Create a single search blob (number + name + row)
    df2["_search"] = (
        df2["BK_Number"].astype(str) + " " +
        df2["BK_name"].astype(str) + " " +
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
        font-weight: 800;
        font-size: 1.1rem;
        background: #00ffc222;
        border: 1px solid #00ffc255;
        color: #00ffc2;
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

    st.markdown("### 🔎 Search Books")
    st.caption("Type book number / name / rack. (No case sensitivity)")

    # --- Pagination state ---
    if "num_results" not in st.session_state:
        st.session_state.num_results = 50

    # Big search box
    st.markdown('<div class="big-search">', unsafe_allow_html=True)
    query = st.text_input(
        "Search",
        placeholder="Start Typing to Search",
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Reset pagination if query changes
    if "last_query" not in st.session_state:
        st.session_state.last_query = ""
    if query != st.session_state.last_query:
        st.session_state.num_results = 50
        st.session_state.last_query = query

    # --- Filtering ---
    def smart_filter(data: pd.DataFrame, q: str) -> pd.DataFrame:
        if not q or not q.strip():
            return data.copy()

        qn = " ".join(q.lower().strip().split())
        # Auto: match across combined blob (number+name+rack)
        return data[data["_search"].str.contains(qn, na=False)]

    all_results = smart_filter(df, query)
    total_found = len(all_results)
    
    # Slice for pagination
    results = all_results.head(st.session_state.num_results)

    st.markdown(f"**Results:** {len(results)} of {total_found}")

    # --- Mobile cards with bright rack ---
    if total_found == 0:
        if query.strip():
            st.warning("No matches found.")
        else:
            st.info("No data available in the sheet.")
    else:
        for _, r in results.iterrows():
            st.markdown(
                f"""
                <div class="result-card">
                  <div class="rowline">
                    <div class="tag-badge">#{r['BK_Number']}<span style="font-size: 0.75rem; opacity: 0.8; font-weight: 400; margin-left: 2px;"></span></div>
                    <div style="display:flex; gap:8px;">
                        <div class="rate-badge">₹ {r['BK_rate']}</div>
                        <div class="rack-badge">📍 {r['BK_row']}</div>
                    </div>
                  </div>
                  <div style="margin-top:16px; font-size:1.4rem; font-weight: 700; line-height: 1.3;">{r['BK_name']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Show More Button
        if total_found > st.session_state.num_results:
            if st.button("🔽 Show More", use_container_width=True):
                st.session_state.num_results += 50
                st.rerun()

        if total_found == 0 and query.strip():
            st.warning("No matches found.")
        elif total_found == 1:
            one = results.iloc[0]
            st.success(f"✅ Location: **{one['BK_row']}**  |  Rate: **₹ {one['BK_rate']}**")
