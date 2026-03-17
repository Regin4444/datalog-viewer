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
    filename = file.name.lower()

    if filename.endswith(".csv"):
        first_line = file.readline().decode("utf-8", errors="ignore").strip()
        file.seek(0)

        if first_line.startswith("#") or "StartTime" in first_line:
            df = pd.read_csv(file, skiprows=1)
        else:
            df = pd.read_csv(file)

    elif filename.endswith(".xlsx"):
        df = pd.read_excel(file)

    else:
        raise ValueError("Unsupported file type. Please upload a CSV or XLSX file.")

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


def prepare_time_axis(df: pd.DataFrame, x_col: str) -> pd.Series:
    source = df[x_col]

    if pd.api.types.is_numeric_dtype(source):
        return pd.to_numeric(source, errors="coerce")

    numeric_try = pd.to_numeric(source, errors="coerce")
    if numeric_try.notna().any():
        return numeric_try

    dt_try = pd.to_datetime(source, errors="coerce")
    if dt_try.notna().any():
        first_valid = dt_try.dropna().iloc[0]
        return (dt_try - first_valid).dt.total_seconds()

    return pd.to_numeric(source, errors="coerce")


def prepare_log_data(df: pd.DataFrame, file_name: str):
    if df.empty:
        raise ValueError(f"{file_name}: file is empty")

    x_col = detect_time_column(df.columns)
    if x_col is None:
        raise ValueError(
            f"{file_name}: could not find a time column. "
            "Accepted time columns: Time (sec), timestamp"
        )

    numeric_df = df.select_dtypes(include=["number"]).copy()

    if x_col in df.columns:
        numeric_df[x_col] = prepare_time_axis(df, x_col)

    numeric_df = numeric_df.dropna(axis=1, how="all")

    if x_col not in numeric_df.columns:
        raise ValueError(f"{file_name}: could not prepare the time axis from '{x_col}'")

    numeric_cols = numeric_df.columns.tolist()
    y_options_all = [c for c in numeric_cols if c != x_col]

    if not y_options_all:
        raise ValueError(f"{file_name}: no numeric columns with usable data were found")

    group_map = build_group_map(y_options_all)
    removed_empty_cols = sorted(list(set(df.select_dtypes(include=["number"]).columns.tolist()) - set(numeric_cols)))

    return {
        "file_name": file_name,
        "df": df,
        "numeric_df": numeric_df,
        "x_col": x_col,
        "y_options_all": y_options_all,
        "group_map": group_map,
        "removed_empty_cols": removed_empty_cols,
    }


def build_overlay_figure(plot_df, x_col, selected_cols, line_width, normalize_overlay, title, ui_revision_key):
    fig = go.Figure()
    y_title = "Value"

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
        height=500,
        title=title,
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
        uirevision=ui_revision_key,
    )
    return fig


def build_stacked_figure(plot_df, x_col, selected_cols, line_width, chart_height_per_row, title, ui_revision_key):
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
        title=title,
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=70, r=30, t=60, b=50),
        uirevision=ui_revision_key,
    )

    fig.update_xaxes(title_text=x_col, row=num_rows, col=1)
    return fig


st.title("📈 ECU Datalog Viewer")
st.caption("Upload up to 2 CSV or XLSX logs, then compare them in stacked graphs.")

uploaded_files = st.file_uploader(
    "Upload 1 or 2 log files",
    type=["csv", "xlsx"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Upload 1 or 2 CSV/XLSX log files to begin.")
    st.stop()

if len(uploaded_files) > 2:
    st.warning("Please upload a maximum of 2 files.")
    st.stop()

logs = []
load_errors = []

for uploaded_file in uploaded_files:
    try:
        df = load_log(uploaded_file)
        log_data = prepare_log_data(df, uploaded_file.name)
        logs.append(log_data)
    except Exception as e:
        load_errors.append(f"{uploaded_file.name}: {e}")

if load_errors:
    for err in load_errors:
        st.error(err)

if not logs:
    st.stop()

# Build common channel list across uploaded files
common_channels = set(logs[0]["y_options_all"])
for log in logs[1:]:
    common_channels &= set(log["y_options_all"])

common_channels = sorted(common_channels)
all_channels_union = sorted(set().union(*[set(log["y_options_all"]) for log in logs]))
group_map_common = build_group_map(common_channels) if common_channels else {}
group_names = ["All Common", "All Available"] + sorted(group_map_common.keys())

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

default_cols = [c for c in preferred_defaults if c in common_channels][:4]
if not default_cols:
    default_cols = common_channels[:4] if common_channels else all_channels_union[:4]

with st.sidebar:
    st.header("Controls")

    view_mode = st.radio("View mode", ["Overlay", "Stacked"], index=0)

    selected_group = st.selectbox("Channel group", group_names, index=0)

    if selected_group == "All Common":
        available_options = common_channels
    elif selected_group == "All Available":
        available_options = all_channels_union
    else:
        available_options = group_map_common.get(selected_group, [])

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

    combined_names = "_".join(sorted([log["file_name"] for log in logs]))
    file_key = f"channels_{combined_names}"

    selected_cols = st.multiselect(
        "Channels",
        options=filtered_options,
        default=default_for_group,
        key=file_key,
        help="Choose channels to plot. If a channel is missing from one file, it will be skipped for that graph."
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
    show_groups = st.checkbox("Show detected common groups", value=False)
    show_columns = st.checkbox("Show common channels", value=False)
    show_ignored = st.checkbox("Show ignored empty channels", value=False)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Files loaded", len(logs))
m2.metric("Common channels", len(common_channels))
m3.metric("Selected", len(selected_cols))
m4.metric("View", view_mode)

if show_groups and group_map_common:
    with st.expander("Detected common channel groups", expanded=True):
        for group_name, cols in group_map_common.items():
            st.markdown(f"**{group_name}** ({len(cols)})")
            st.write(cols)

if show_columns:
    with st.expander("Common channels", expanded=True):
        st.write(common_channels)

if show_ignored:
    with st.expander("Ignored empty numeric channels", expanded=True):
        for log in logs:
            st.markdown(f"**{log['file_name']}**")
            st.write(log["removed_empty_cols"] if log["removed_empty_cols"] else ["None"])

if not selected_cols:
    st.warning("Select at least one channel from the sidebar.")
    st.stop()

for idx, log in enumerate(logs, start=1):
    file_name = log["file_name"]
    x_col = log["x_col"]
    numeric_df = log["numeric_df"]

    valid_selected_cols = [col for col in selected_cols if col in numeric_df.columns]
    missing_selected_cols = [col for col in selected_cols if col not in numeric_df.columns]

    st.subheader(f"Log {idx}: {file_name}")

    info1, info2, info3 = st.columns(3)
    info1.metric("Rows", len(log["df"]))
    info2.metric("Usable channels", len(log["y_options_all"]))
    info3.metric("Time axis", x_col)

    if missing_selected_cols:
        st.warning(
            f"{file_name}: these selected channels are not available and were skipped: "
            + ", ".join(missing_selected_cols)
        )

    if show_preview:
        st.dataframe(log["df"].head(20), use_container_width=True)

    if not valid_selected_cols:
        st.info(f"{file_name}: no valid selected channels available to plot.")
        continue

    plot_df = numeric_df[[x_col] + valid_selected_cols].copy()
    plot_df = plot_df.sort_values(by=x_col)

    ui_revision_key = f"{file_name}_{x_col}_{view_mode}"

    if view_mode == "Stacked":
        fig = build_stacked_figure(
            plot_df=plot_df,
            x_col=x_col,
            selected_cols=valid_selected_cols,
            line_width=line_width,
            chart_height_per_row=chart_height_per_row,
            title=f"Stacked Channel View — {file_name}",
            ui_revision_key=ui_revision_key,
        )
    else:
        fig = build_overlay_figure(
            plot_df=plot_df,
            x_col=x_col,
            selected_cols=valid_selected_cols,
            line_width=line_width,
            normalize_overlay=normalize_overlay,
            title=f"Overlay Channel View — {file_name}",
            ui_revision_key=ui_revision_key,
        )

    st.plotly_chart(fig, use_container_width=True)
