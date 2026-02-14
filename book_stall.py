import streamlit as st
import pandas as pd
import re
import json
from pathlib import Path

st.set_page_config(page_title="BK Search Pro", layout="centered")  # better for phone

CONFIG_PATH = Path("config.json")
ADMIN_PASSWORD = "mother"

APP_FIELDS = ["BK_Number", "BK_name", "BK_row"]  # standard names inside the app


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
                else:
                    st.error("❌ Wrong password")
        with c2:
            if st.button("Cancel"):
                st.session_state.show_admin_login = False


# ---------------------------
# Load sheet (if configured)
# ---------------------------
sheet_id = extract_sheet_id(cfg.get("sheet_url", ""))
df_raw, load_error = None, None

if sheet_id and cfg.get("sheet_name"):
    try:
        df_raw = fetch_sheet_df(sheet_id, cfg["sheet_name"])
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
        st.subheader("Setup Google Sheet + Dynamic Column Mapping")

        new_url = st.text_input("Google Sheet Link", value=cfg.get("sheet_url", ""))
        new_sheet_name = st.text_input("Sheet Tab Name", value=cfg.get("sheet_name", "Sheet1"))
        st.caption("Make sure sharing: Anyone with link → Viewer")

        preview_df, preview_error = None, None
        preview_id = extract_sheet_id(new_url)
        if preview_id and new_sheet_name:
            try:
                preview_df = fetch_sheet_df(preview_id, new_sheet_name)
            except Exception as e:
                preview_error = str(e)

        if not preview_id:
            st.info("Paste a valid Google Sheet link to continue.")
        elif preview_error:
            st.error(f"Could not load sheet: {preview_error}")
        else:
            st.success("✅ Sheet columns detected")
            sheet_cols = preview_df.columns.tolist()

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
                mapped_preview = apply_mapping(preview_df, new_mapping)
                st.dataframe(mapped_preview[APP_FIELDS], width="stretch", height=250)
            except Exception as e:
                st.info(f"Preview not ready: {e}")

            if st.button("💾 Save Configuration", type="primary"):
                cfg["sheet_url"] = new_url
                cfg["sheet_name"] = new_sheet_name
                cfg["mapping"] = new_mapping
                save_config(cfg)
                st.cache_data.clear()
                st.success("✅ Saved locally!")
                st.info("💡 **Tip:** To keep these settings permanently (even after rehosting), make sure to **commit and push** your changes to GitHub.")

# ---------------------------
# USER SEARCH (mobile-first)
# ---------------------------
st.divider()

if not cfg.get("sheet_url") or not cfg.get("sheet_name"):
    st.warning("Admin has not configured the Google Sheet yet. Tap Admin → Setup & Mapping.")
elif load_error:
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
        placeholder="Type: 1 or test or AA1 ...",
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
                    <div><b>#{r['BK_Number']}</b> <span class="tiny">Book No</span></div>
                    <div class="rack-badge">📍 {r['BK_row']}</div>
                  </div>
                  <div style="margin-top:8px; font-size:1.05rem;"><b>{r['BK_name']}</b></div>
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
            st.success(f"✅ Location: **{one['BK_row']}**  |  Book: **{one['BK_name']}** (#{one['BK_Number']})")
