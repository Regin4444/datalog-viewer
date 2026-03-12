import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import Counter

st.set_page_config(page_title="Car Log Viewer", layout="wide")

st.title("Remap Data Log Viewer")


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

    cleaned_cols = [str(c).strip() for c in df.columns]
    df.columns = make_unique_columns(cleaned_cols)

    # Replace common blank/missing placeholders
    df = df.replace(["-", "--", "---", ""], pd.NA)

    # Convert columns to numeric where possible
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")

    return df


def get_channel_group(col_name: str) -> str:
    c = col_name.lower()

    rules = [
        ("Time", ["time", "timestamp"]),
        ("RPM / Speed", ["rpm", "engine speed", "vehicle speed", "speed"]),
        ("Boost / Air", [
            "boost", "map", "charge", "intake", "turbo", "air mass", "mass air", "maf",
            "manifold", "baro", "pressure upstream", "air pressure"
        ]),
        ("Fueling / Lambda", [
            "lambda", "afr", "fuel", "injection", "injector", "rail pressure",
            "fuel trim", "trim", "ltft", "stft"
        ]),
        ("Ignition", [
            "ignition", "spark", "timing", "knock", "misfire", "cylinder retard", "retard"
        ]),
        ("Throttle / Torque / Load", [
            "throttle", "pedal", "torque", "load", "driver request", "requested torque"
        ]),
        ("Temperatures", [
            "temp", "temperature", "coolant", "oil temp", "iat", "egt", "catalyst"
        ]),
        ("Exhaust / Emissions", [
            "exhaust", "cat", "catalyst", "o2", "oxygen", "emission", "particulate"
        ]),
        ("Cam / VVT", [
            "cam", "vvt", "valve", "phaser"
        ]),
        ("Transmission / Drivetrain", [
            "gear", "clutch", "transmission", "tcu", "drivetrain"
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

    # Sort channels inside each group
    for group in group_map:
        group_map[group] = sorted(group_map[group])

    return dict(sorted(group_map.items(), key=lambda x: x[0]))


uploaded_file = st.file_uploader("Upload CSV log", type=["csv"])

if uploaded_file is not None:
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

    # Only keep numeric columns
    numeric_df = df.select_dtypes(include=["number"]).copy()

    # Remove columns with no usable data
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
        "Mass air flow",
    ]

    default_cols = [c for c in preferred_defaults if c in y_options_all][:4]
    if not default_cols:
        default_cols = y_options_all[:3]

    removed_empty_cols = sorted(
        list(set(df.select_dtypes(include=["number"]).columns.tolist()) - set(numeric_cols))
    )

    left, right = st.columns([2, 1])

    with left:
        selected_group = st.selectbox("Channel group", group_names, index=0)

        if selected_group == "All":
            available_options = y_options_all
        else:
            available_options = group_map.get(selected_group, [])

        default_for_group = [c for c in default_cols if c in available_options]
        if not default_for_group:
            default_for_group = available_options[: min(3, len(available_options))]

        selected_cols = st.multiselect(
            "Select columns to plot",
            options=available_options,
            default=default_for_group,
        )

    with right:
        show_preview = st.checkbox("Show data preview", value=True)
        show_groups = st.checkbox("Show channel groups", value=False)
        show_ignored = st.checkbox("Show ignored empty channels", value=False)

    st.caption(f"Using time column: **{x_col}**")

    if show_preview:
        st.subheader("Preview")
        st.dataframe(df.head(), use_container_width=True)

    if show_groups:
        with st.expander("Detected channel groups", expanded=True):
            for group_name, cols in group_map.items():
                st.markdown(f"**{group_name}** ({len(cols)})")
                st.write(cols)

    if show_ignored and removed_empty_cols:
        with st.expander("Ignored empty numeric channels", expanded=True):
            st.write(removed_empty_cols)

    if not selected_cols:
        st.info("Select at least one channel to display.")
        st.stop()

    fig = go.Figure()

    for i, col in enumerate(selected_cols):
        axis_name = "y" if i == 0 else f"y{i+1}"

        fig.add_trace(
            go.Scatter(
                x=df[x_col],
                y=df[col],
                mode="lines",
                name=col,
                yaxis=axis_name,
                hovertemplate=(
                    f"<b>{col}</b><br>"
                    f"{x_col}: %{{x}}<br>"
                    f"Value: %{{y}}<extra></extra>"
                ),
            )
        )

    layout = {
        "title": "Selected Log Channels",
        "height": 700,
        "xaxis": {"title": x_col},
        "yaxis": {"title": selected_cols[0]},
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        "margin": {
            "l": 80,
            "r": 220,
            "t": 80,
            "b": 60,
        },
        "hovermode": "x unified",
    }

    extra_count = len(selected_cols) - 1

    for i, col in enumerate(selected_cols[1:], start=2):
        if extra_count == 1:
            position = 0.98
        else:
            step = 0.13 / (extra_count - 1)
            position = 0.85 + (i - 2) * step

        layout[f"yaxis{i}"] = {
            "title": col,
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": position,
        }

    fig.update_layout(layout)

    st.plotly_chart(fig, use_container_width=True)

    if len(selected_cols) > 6:
        st.warning(
            "Displaying more than 6 channels with separate Y-axes can become hard to read. "
            "Stacked subplots are usually better for larger selections."
        )

else:
    st.info("Upload a CSV log file to begin.")