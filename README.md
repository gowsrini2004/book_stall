# 📚 BK Search Pro

A mobile-friendly Streamlit application for searching books from a Google Sheets source.

## Features
- **Fast Search**: Search by Book Number, Name, or Rack/Row.
- **Dynamic Configuration**: Admin panel to set Google Sheet URL and map columns.
- **Mobile Optimized**: Clean interface designed for handheld devices.
- **Admin Access**: Protected settings for sheet management.

## Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/gowsrini2004/book_stall.git
   cd book_stall
   ```

2. **Create and activate a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install streamlit pandas
   ```

4. **Run the app**:
   ```bash
   streamlit run book_stall.py
   ```

## Configuration
Access the **Admin Panel** (⚙️ icon) to:
- Paste your Google Sheet URL.
- Map your sheet's columns to `BK_Number`, `BK_name`, and `BK_row`.
- Save the configuration to `config.json`.
