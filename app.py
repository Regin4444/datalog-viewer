import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from collections import Counter

st.set_page_config(
    page_title="Datalog Viewer",
    page_icon="📈",
    layout="wide"
)


def make_unique_columns(columns):
    counts = Counter()
    new_cols = []

    for col in columns:
        col = str(col).strip()
        counts[col] += 1

        if counts[col] == 1:
            new_cols.append(col)
        else:
            new_cols.append(f"{col} ({counts[col]})")

    return new_cols


def detect_time_column(columns):
    preferred_names = [
        "Time (sec)",
        "timestamp",
        "Timestamp",
        "time",
        "Time",
    ]

    for name in preferred_names:
        if name in columns:
            return name

    return None


def load_log(file) -> pd.DataFrame:
    first_line = file.readline().decode("utf-8", errors="ignore").strip()
    file.seek(0)

    if first_line.startswith("#") or "StartTime" in first_line:
        df = pd.read_csv(file, skiprows=1)
    else:
        df = pd.read_csv(file)

    df.columns = make_unique_columns(df.columns)

    # Common missing / blank placeholders
    df = df.replace(["-", "--", "---", ""], pd.NA)

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")

    return df


def get_channel_group(col_name: str) -> str:
    c = col_name.lower()

    rules = [
        ("RPM / Speed", ["rpm", "engine speed", "vehicle speed", "speed"]),
        ("Boost / Air", [
            "boost", "map", "charge", "intake", "turbo", "air mass", "mass air",
            "maf", "manifold", "baro", "pressure", "air pressure"
        ]),
        ("Fueling / Lambda", [
            "lambda", "afr", "fuel", "injection", "injector",
            "rail pressure", "fuel trim", "trim", "ltft", "stft"
        ]),
        ("Ignition", [
            "ignition", "spark", "timing", "knock", "retard", "misfire"
        ]),
        ("Throttle / Torque / Load", [
            "throttle", "pedal", "torque", "load", "driver request"
        ]),
        ("Temperatures", [
            "temp", "temperature", "coolant", "oil", "iat", "egt", "catalyst"
        ]),
        ("Cam / VVT", [
            "cam", "vvt", "valve", "phaser"
        ]),
        ("Transmission / Drivetrain", [
            "gear", "clutch", "transmission", "drivetrain"
        ]),
        ("Electrical", [
            "voltage", "battery", "current", "alternator"
        ]),
        ("Diagnostics / Status", [
            "status", "state", "mode", "error", "fault", "counter", "flag"
        ]),
    ]

    for group_name, keywords in rules:
        if any(keyword in c for keyword in keywords):
            return group_name

    return "Other"


def build_group_map(columns):
    group_map = {}
    for col in columns:
        group = get_channel_group(col)
        group_map.setdefault(group, []).append(col)

    for group in group_map:
        group_map[group] = sorted(group_map[group])

    return dict(sorted(group_map.items(), key=lambda x: x[0]))


def normalize_series(series: pd.Series) -> pd.Series:
    col_min = series.min()
    col_max = series.max()

    if pd.notna(col_min) and pd.notna(col_max) and col_max != col_min:
        return (series - col_min) / (col_max - col_min)

    return pd.Series([0] * len(series), index=series.index)


st.title("📈 ECU Datalog Viewer")
st.caption("Upload a CSV log, group channels, and inspect them in overlay or stacked view.")

uploaded_file = st.file_uploader("Upload CSV log", type=["csv"])

if uploaded_file is None:
    st.info("Upload a CSV log file to begin.")
    st.stop()

try:
    df = load_log(uploaded_file)
except Exception as e:
    st.error(f"Failed to read file: {e}")
    st.stop()

if df.empty:
    st.error("The uploaded file appears to be empty.")
    st.stop()

x_col = detect_time_column(df.columns)

if x_col is None:
    st.error("Could not find a time column in this file.")
    st.write("Accepted time columns: `Time (sec)` or `timestamp`")
    st.write("Detected columns:", list(df.columns))
    st.stop()

# Keep numeric columns only
numeric_df = df.select_dtypes(include=["number"]).copy()

# Remove columns with no actual data
numeric_df = numeric_df.dropna(axis=1, how="all")

# Ensure x-axis column exists in numeric data if possible
if x_col not in numeric_df.columns and x_col in df.columns:
    numeric_df[x_col] = pd.to_numeric(df[x_col], errors="coerce")

numeric_df = numeric_df.dropna(axis=1, how="all")

numeric_cols = numeric_df.columns.tolist()
y_options_all = [c for c in numeric_cols if c != x_col]

if not y_options_all:
    st.error("No numeric columns with usable data were found to plot.")
    st.stop()

group_map = build_group_map(y_options_all)
group_names = ["All"] + list(group_map.keys())

preferred_defaults = [
    "Engine RPM (RPM)",
    "Engine speed",
    "Boost (psi)",
    "Boost pressure",
    "Boost pressure (2)",
    "Lambda (AFR)",
    "Lambda (AFR) setpoint",
    "A/F Commanded",
    "Ignition advance",
    "Throttle valve position",
]

default_cols = [c for c in preferred_defaults if c in y_options_all][:4]
if not default_cols:
    default_cols = y_options_all[:4]

all_numeric_original = df.select_dtypes(include=["number"]).columns.tolist()
removed_empty_cols = sorted(list(set(all_numeric_original) - set(numeric_cols)))

with st.sidebar:
    st.header("Controls")

    view_mode = st.radio("View mode", ["Overlay", "Stacked"], index=0)

    selected_group = st.selectbox("Channel group", group_names, index=0)

    if selected_group == "All":
        available_options = y_options_all
    else:
        available_options = group_map.get(selected_group, [])

    search_text = st.text_input("Search channels", placeholder="e.g. boost, lambda, rpm")

    if search_text:
        filtered_options = [
            c for c in available_options
            if search_text.lower() in c.lower()
        ]
    else:
        filtered_options = available_options

    default_for_group = [c for c in default_cols if c in filtered_options]
    if not default_for_group and filtered_options:
        default_for_group = filtered_options[:min(4, len(filtered_options))]

    selected_cols = st.multiselect(
        "Channels",
        options=filtered_options,
        default=default_for_group,
    )

    st.divider()

    normalize_overlay = False
    if view_mode == "Overlay":
        normalize_overlay = st.checkbox("Normalize overlay channels", value=True)

    line_width = st.slider("Line width", 1, 5, 2, 1)

    if view_mode == "Stacked":
        chart_height_per_row = st.slider("Height per chart", 180, 400, 240, 10)
    else:
        chart_height_per_row = 240

    show_preview = st.checkbox("Show data preview", value=False)
    show_groups = st.checkbox("Show detected groups", value=False)
    show_columns = st.checkbox("Show detected columns", value=False)
    show_ignored = st.checkbox("Show ignored empty channels", value=False)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows", len(df))
c2.metric("Usable channels", len(y_options_all))
c3.metric("Selected", len(selected_cols))
c4.metric("Time axis", x_col)

if show_preview:
    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

if show_groups:
    with st.expander("Detected channel groups", expanded=True):
        for group_name, cols in group_map.items():
            st.markdown(f"**{group_name}** ({len(cols)})")
            st.write(cols)

if show_columns:
    with st.expander("Detected usable numeric columns", expanded=True):
        st.write(y_options_all)

if show_ignored and removed_empty_cols:
    with st.expander("Ignored empty numeric channels", expanded=True):
        st.write(removed_empty_cols)

if not selected_cols:
    st.warning("Select at least one channel from the sidebar.")
    st.stop()

plot_df = numeric_df[[x_col] + selected_cols].copy()
plot_df = plot_df.sort_values(by=x_col)

if view_mode == "Stacked":
    num_rows = len(selected_cols)

    fig = make_subplots(
        rows=num_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=selected_cols
    )

    for i, col in enumerate(selected_cols, start=1):
        fig.add_trace(
            go.Scatter(
                x=plot_df[x_col],
                y=plot_df[col],
                mode="lines",
                name=col,
                line={"width": line_width},
                hovertemplate=(
                    f"<b>{col}</b><br>"
                    f"{x_col}: %{{x}}<br>"
                    f"Value: %{{y}}<extra></extra>"
                ),
            ),
            row=i,
            col=1
        )

        fig.update_yaxes(title_text=col, row=i, col=1)

    total_height = max(350, num_rows * chart_height_per_row)

    fig.update_layout(
        height=total_height,
        title="Stacked Channel View",
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=70, r=30, t=60, b=50),
    )

    fig.update_xaxes(title_text=x_col, row=num_rows, col=1)

else:
    fig = go.Figure()

    for col in selected_cols:
        actual_y = plot_df[col]

        if normalize_overlay:
            displayed_y = normalize_series(actual_y)
            y_title = "Normalized value"
        else:
            displayed_y = actual_y
            y_title = "Value"

        fig.add_trace(
            go.Scatter(
                x=plot_df[x_col],
                y=displayed_y,
                mode="lines",
                name=col,
                line={"width": line_width},
                customdata=actual_y,
                hovertemplate=(
                    f"<b>{col}</b><br>"
                    f"{x_col}: %{{x}}<br>"
                    f"Actual: %{{customdata}}<br>"
                    f"Displayed: %{{y}}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        height=max(500, chart_height_per_row * 2),
        title="Overlay Channel View",
        hovermode="x unified",
        margin=dict(l=70, r=30, t=60, b=50),
        yaxis_title=y_title,
        xaxis_title=x_col,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
    )

st.plotly_chart(fig, use_container_width=True)
