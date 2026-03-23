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
from mesa.visualization import SolaraViz, make_plot_component, make_space_component
from mesa.visualization.utils import update_counter
from agents import greenAgent, yellowAgent, redAgent
from objects import radioactivityAgent, wasteAgent
# Import the local MoneyModel.py
from model import Model


def robotAgent_portrayal(robotAgent):
    color = "tab:blue"
    if isinstance(robotAgent, greenAgent):
        color = "tab:green"
    elif isinstance(robotAgent, yellowAgent):
        color = "tab:orange"
    elif isinstance(robotAgent, redAgent):
        color = "tab:red"

    return {
        "size": 800,
        "color": color,
        "marker": "s",
        "zorder": 2,
    }

def wasteAgent_portrayal(wasteAgent):
    if wasteAgent.waste_type == "green":
        color = "#096C0F"
    elif wasteAgent.waste_type == "yellow":
        color = "#B8AC06"
    elif wasteAgent.waste_type == "red":
        color = "#A80303"
    return {
        "size": 600,
        "color": color,
        "marker": "o",
        "zorder": 1,
    }

def radioactivityAgent_portrayal(radioactivityAgent):
    """Portrayal for radioactivity agents based on their level."""
    # Color based on radioactivity level
    if radioactivityAgent.radioactivity < 0.33:
        color = "lightgreen"
    elif radioactivityAgent.radioactivity < 0.66:
        color = "lightyellow"
    elif radioactivityAgent.radioactivity < 1:
        color = "lightcoral"
    else:  # Waste Disposal Zone
        color = "purple"
    
    marker = "s"
    if radioactivityAgent.radioactivity == 4:
        marker = "^" 
    
    return {
        "marker": marker,
        "size": 1000,
        "color": color,
        "zorder": 0
    }

def agent_portrayal(agent):
    """General portrayal function that handles all agent types."""
    if isinstance(agent, radioactivityAgent):
        return radioactivityAgent_portrayal(agent)
    elif isinstance(agent, wasteAgent):
        return wasteAgent_portrayal(agent)
    elif isinstance(agent, (greenAgent, yellowAgent, redAgent)):
        return robotAgent_portrayal(agent)
    return {"size": 1, "color": "gray"}

@solara.component
def WasteCountPlot(model):
    """Plot showing the evolution of waste counts over time."""
    update_counter.get()  # This is required to update the counter
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
    """Plot showing the cumulative distance of all waste to the disposal zone."""
    update_counter.get()  # This is required to update the counter
    fig = Figure(figsize=(10, 5))
    ax = fig.subplots()
    
    if model.cumulative_distance_history:
        steps = [record["step"] for record in model.cumulative_distance_history]
        distances = [record["distance"] for record in model.cumulative_distance_history]
        
        ax.plot(steps, distances, label="Cumulative Distance", color="purple", linewidth=2)
        
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
        "max": 100,
        "step": 1,
    },
    "n_yellow_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of yellow agents:",
        "min": 0,
        "max": 100,
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
    "n_waste": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of waste:",
        "min": 0,
        "max": 100,
        "step": 1,
    },
    "width": {
        "type": "SliderInt",
        "value": 30,
        "label": "Width:",
        "min": 5,
        "max": 500,
        "step": 1,
    },
    "height": {
        "type": "SliderInt",
        "value": 30,
        "label": "Height:",
        "min": 5,
        "max": 500,
        "step": 1,
    }
}

# Create initial model instance
model = Model(n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_waste=10, width=10, height=10)

SpaceGraph = make_space_component(agent_portrayal)

#Create the Dashboard
page = SolaraViz(
    model,
    components=[SpaceGraph, WasteCountPlot, CumulativeDistancePlot],
    model_params=model_params,
    name="Radioactive Waste Collection",
)
# This is required to render the visualization in the Jupyter notebook
page
# to start : "solara run server.py"