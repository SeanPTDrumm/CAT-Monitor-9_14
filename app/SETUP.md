# Catastrophe Monitor — Setup Instructions

## Quick Start

### Prerequisites
- Python 3.9+
- pip (Python package manager)

### Installation

1. **Extract the ZIP file** to your desired location

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   streamlit run app.py
   ```

5. **Open in browser**:
   - The app should automatically open at `http://localhost:8501`
   - If not, navigate there manually

---

## Project Structure

```
catastrophe-monitor/
├── app.py                 # Main Streamlit app entry point
├── requirements.txt       # Python dependencies
├── README.md             # Product documentation
├── SETUP.md              # This file
├── CATASTROPHE_MONITOR_HANDOFF.md  # Architecture & status
│
├── Core Modules
├── wfigs.py              # WFIGS CSV ingestion
├── snapshots.py          # Snapshot management and comparison
├── baseline.py           # Justin's baseline state
├── analyst.py            # Analyst decision persistence
├── screening.py          # Urgency screening logic
├── urgency.py            # Urgency calculations
│
├── Geographic/Mapping
├── maps.py               # Pydeck map rendering
├── dashboard_map.py      # Dashboard-specific map renderer
├── geo/
│   ├── analysis.py       # Perimeter retrieval, ZCTA calculations
│   ├── spatial.py        # Polygon operations, distance calculations
│   ├── census.py         # Population data
│   ├── perimeters.py     # NIFC perimeter processing
│   ├── zipmaster.py      # ZIP/ZCTA data management
│   └── net.py            # Network requests
│
├── UI/Presentation
├── dashboard.py          # Dashboard page components
├── theme.py              # Visual theme/styling
├── attention.py          # Attention/urgency UI logic
├── reviews.py            # Review queue logic
├── bands.py              # UI bands/sections
│
└── data/
    └── snapshots/        # (Created at runtime) Analyst records & snapshots
```

---

## First Time Use

### Load Sample Data

1. Click **"Data"** dropdown in top right
2. Select **"Upload files"** or **"Import from project folder"**
3. Upload a WFIGS CSV file (download from NIFC website)
4. The app will ingest and create a snapshot

### Try Comparison

1. Load a second WFIGS CSV file (from a different date)
2. In sidebar under **"Snapshots"**, select:
   - **Current snapshot** → newer file
   - **Compare with prior snapshot** → older file
3. Dashboard will show what changed

### Navigate

- **Dashboard** — Overview of fires needing attention
- **Fire Table** — Browse all fires with sorting/filtering
- **Fire Detail** — Deep dive into a specific fire with map, notes, moratorium tracking

---

## Data Storage

- **Local storage only**: `data/snapshots/` folder
- Contains analyst decisions, notes, moratorium data
- Not included in ZIP (see `.gitignore`)
- Safe to delete and restart; WFIGS data can be re-uploaded

---

## Troubleshooting

### "No snapshots loaded yet"
- Upload a WFIGS CSV file via the **"Data"** dropdown

### Map not showing
- Click on a fire in the list, then click **"Open Fire Detail"** to view full map

### Comparison not working
- You need at least 2 uploaded CSV files to compare
- Select them in sidebar under **"Snapshots"**

### Dependency errors
- Ensure you're in the correct virtual environment
- Run: `pip install -r requirements.txt` again

---

## For Design/Architecture Review

See **CATASTROPHE_MONITOR_HANDOFF.md** for:
- Current architecture overview
- UI/backend coupling issues
- Desired separation of concerns
- Product requirements and decisions
- Known risks

---

## Questions?

- **Product goal**: See README.md
- **Architecture**: See CATASTROPHE_MONITOR_HANDOFF.md
- **Code details**: Read the source files (all Python, well-commented)
