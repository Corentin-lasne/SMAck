""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

import mesa
import solara
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from mesa.visualization import SolaraViz
from mesa.visualization.utils import update_counter
from agents import greenAgent, yellowAgent, redAgent
from objects import wasteAgent
from model import Model

ZONE_COLORS = {
    "z1": "#d9f7be",  # green-tinted
    "z2": "#fff1b8",  # amber-tinted
    "z3": "#ffd6d6",  # red-tinted
}

ROBOT_COLORS = {
    "green": "#2f9e44",
    "yellow": "#f08c00",
    "red": "#c92a2a",
}

WASTE_COLORS = {
    "green": "#1b5e20",
    "yellow": "#f59f00",
    "red": "#a61e4d",
}


def _robot_role(robot):
    """Return the role key used by color maps."""
    if isinstance(robot, greenAgent):
        return "green"
    if isinstance(robot, yellowAgent):
        return "yellow"
    return "red"


def _carried_waste_type(robot):
    """Return the first carried waste type, or `None` when inventory is empty."""
    if not getattr(robot, "inventory", None):
        return None
    return robot.inventory[0].waste_type


def _waste_offsets(count):
    """Return deterministic marker offsets to keep multiple wastes readable in one cell."""
    base = [
        (0.0, 0.0),
        (-0.18, 0.18),
        (0.18, 0.18),
        (-0.18, -0.18),
        (0.18, -0.18),
        (0.0, 0.24),
        (0.0, -0.24),
        (-0.24, 0.0),
        (0.24, 0.0),
    ]
    if count <= len(base):
        return base[:count]
    return [base[i % len(base)] for i in range(count)]


@solara.component
def SpaceGraph(model):
    """Render the grid with clear zone background, cell borders, and readable overlays."""
    update_counter.get()
    width, height = model.grid.width, model.grid.height

    fig = Figure(
        figsize=(
            max(8, min(16, width * 0.38)),
            max(6, min(14, height * 0.38)),
        )
    )
    ax = fig.subplots()
    ax.set_facecolor("#f8f9fa")

    # Draw zone backgrounds first for immediate spatial context.
    zone_specs = [
        (model.z1, ZONE_COLORS["z1"]),
        (model.z2, ZONE_COLORS["z2"]),
        (model.z3, ZONE_COLORS["z3"]),
    ]
    for (x_min, y_min, x_max, y_max), zone_color in zone_specs:
        ax.add_patch(
            Rectangle(
                (x_min - 0.5, y_min - 0.5),
                x_max - x_min,
                y_max - y_min,
                facecolor=zone_color,
                edgecolor="none",
                alpha=0.9,
                zorder=0,
            )
        )

    # Highlight disposal position as a stable landmark.
    disp_x, disp_y = model.waste_disposal_zone
    ax.add_patch(
        Rectangle(
            (disp_x - 0.5, disp_y - 0.5),
            1,
            1,
            facecolor="none",
            edgecolor="#111827",
            linewidth=2.2,
            zorder=2,
        )
    )
    ax.scatter(
        [disp_x],
        [disp_y],
        marker="X",
        s=180,
        c="#111827",
        edgecolors="white",
        linewidths=1.0,
        zorder=3,
    )

    # Render wastes first, then robots on top.
    for x in range(width):
        for y in range(height):
            cell_contents = model.grid.get_cell_list_contents([(x, y)])
            wastes = [obj for obj in cell_contents if isinstance(obj, wasteAgent)]
            robots = [obj for obj in cell_contents if isinstance(obj, (greenAgent, yellowAgent, redAgent))]

            offsets = _waste_offsets(len(wastes))
            for waste, (dx, dy) in zip(wastes, offsets):
                ax.scatter(
                    [x + dx],
                    [y + dy],
                    marker="o",
                    s=80,
                    c=WASTE_COLORS[waste.waste_type],
                    edgecolors="#111827",
                    linewidths=0.8,
                    zorder=4,
                )

            if robots:
                robot = robots[0]
                role = _robot_role(robot)
                carried = _carried_waste_type(robot)
                edge_color = WASTE_COLORS[carried] if carried else "#ffffff"
                edge_width = 2.6 if carried else 1.2

                ax.scatter(
                    [x],
                    [y],
                    marker="s",
                    s=260,
                    c=ROBOT_COLORS[role],
                    edgecolors=edge_color,
                    linewidths=edge_width,
                    zorder=6,
                )

                # Badge shows carried waste type at a glance.
                if carried:
                    ax.scatter(
                        [x + 0.22],
                        [y + 0.22],
                        marker="o",
                        s=55,
                        c=WASTE_COLORS[carried],
                        edgecolors="#111827",
                        linewidths=0.8,
                        zorder=7,
                    )

    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(-0.5, height - 0.5)
    ax.set_aspect("equal")

    # Visible cell borders for readability.
    ax.set_xticks([i - 0.5 for i in range(width + 1)], minor=True)
    ax.set_yticks([i - 0.5 for i in range(height + 1)], minor=True)
    ax.grid(which="minor", color="#475569", alpha=0.45, linewidth=0.45)

    ax.set_xticks(range(0, width, max(1, width // 10)))
    ax.set_yticks(range(0, height, max(1, height // 10)))
    ax.tick_params(axis="both", labelsize=8, colors="#111827")

    legend_handles = [
        Patch(facecolor=ZONE_COLORS["z1"], edgecolor="none", label="Zone 1"),
        Patch(facecolor=ZONE_COLORS["z2"], edgecolor="none", label="Zone 2"),
        Patch(facecolor=ZONE_COLORS["z3"], edgecolor="none", label="Zone 3"),
        Line2D([0], [0], marker="s", markersize=8, color="w", markerfacecolor=ROBOT_COLORS["green"], label="Green agent"),
        Line2D([0], [0], marker="s", markersize=8, color="w", markerfacecolor=ROBOT_COLORS["yellow"], label="Yellow agent"),
        Line2D([0], [0], marker="s", markersize=8, color="w", markerfacecolor=ROBOT_COLORS["red"], label="Red agent"),
        Line2D([0], [0], marker="o", markersize=7, color="w", markerfacecolor=WASTE_COLORS["green"], markeredgecolor="#111827", label="Green waste"),
        Line2D([0], [0], marker="o", markersize=7, color="w", markerfacecolor=WASTE_COLORS["yellow"], markeredgecolor="#111827", label="Yellow waste"),
        Line2D([0], [0], marker="o", markersize=7, color="w", markerfacecolor=WASTE_COLORS["red"], markeredgecolor="#111827", label="Red waste"),
        Line2D([0], [0], marker="s", markersize=8, color="w", markerfacecolor="#9ca3af", markeredgecolor=WASTE_COLORS["green"], markeredgewidth=2, label="Carrying waste"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=5,
        fontsize=7,
        frameon=True,
    )

    ax.set_title("Grid State", fontsize=11, color="#111827")
    solara.FigureMatplotlib(fig)

@solara.component
def WasteCountPlot(model):
    """Plot the number of wastes by type and in total over time."""
    update_counter.get()
    fig = Figure(figsize=(10, 5))
    ax = fig.subplots()
    
    if model.waste_count_history:
        steps = [record["step"] for record in model.waste_count_history]
        green = [record["green"] for record in model.waste_count_history]
        yellow = [record["yellow"] for record in model.waste_count_history]
        red = [record["red"] for record in model.waste_count_history]
        total = [record["total"] for record in model.waste_count_history]
        
        ax.plot(steps, green, label="Green", color="#096C0F", linewidth=2)
        ax.plot(steps, yellow, label="Yellow", color="#B8AC06", linewidth=2)
        ax.plot(steps, red, label="Red", color="#A80303", linewidth=2)
        ax.plot(steps, total, label="Total", color="black", linewidth=2, linestyle="--")
        
        ax.set_xlabel("Step")
        ax.set_ylabel("Number of Waste")
        ax.set_title("Waste Count Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    solara.FigureMatplotlib(fig)

@solara.component
def CumulativeDistancePlot(model):
    """Plot cumulative Manhattan distance from all wastes to disposal."""
    update_counter.get()
    fig = Figure(figsize=(10, 5))
    ax = fig.subplots()
    
    if model.cumulative_distance_history:
        steps = [record["step"] for record in model.cumulative_distance_history]
        distances = [record["distance"] for record in model.cumulative_distance_history]
        
        ax.plot(steps, distances, label="Cumulative Distance", color="#5f3dc4", linewidth=2)
        
        ax.set_xlabel("Step")
        ax.set_ylabel("Cumulative Distance (Manhattan)")
        ax.set_title("Cumulative Distance of Waste to Disposal Zone")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    solara.FigureMatplotlib(fig)

model_params = {
    "n_green_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of green agents:",
        "min": 0,
        "max": 30,
        "step": 1,
    },
    "n_yellow_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of yellow agents:",
        "min": 0,
        "max": 30,
        "step": 1,
    },
    "n_red_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of red agents:",
        "min": 0,
        "max": 10,
        "step": 1,
    },
    "n_green_waste": {
        "type": "SliderInt",
        "value": 10,
        "label": "Initial Green Waste:",
        "min": 0,
        "max": 50,
        "step": 1,
    },
    "n_yellow_waste": {
        "type": "SliderInt",
        "value": 0,
        "label": "Initial Yellow Waste:",
        "min": 0,
        "max": 50,
        "step": 1,
    },
    "n_red_waste": {
        "type": "SliderInt",
        "value": 0,
        "label": "Initial Red Waste:",
        "min": 0,
        "max": 50,
        "step": 1,
    },
    "width": {
        "type": "SliderInt",
        "value": 30,
        "label": "Width:",
        "min": 5,
        "max": 50,
        "step": 1,
    },
    "height": {
        "type": "SliderInt",
        "value": 30,
        "label": "Height:",
        "min": 5,
        "max": 50,
        "step": 1,
    }
}

# Create initial model instance used by SolaraViz.
model = Model(n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_green_waste=10, n_yellow_waste=0, n_red_waste=0, width=30, height=30)

# Build dashboard components around model controls and live plots.
page = SolaraViz(
    model,
    components=[SpaceGraph, WasteCountPlot, CumulativeDistancePlot],
    model_params=model_params,
    name="Radioactive Waste Collection",
)
# to start : "solara run server.py"