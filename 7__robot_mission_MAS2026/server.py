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
    size = 10
    color = "tab:blue"
    if isinstance(robotAgent, greenAgent):
        color = "tab:green"
    elif isinstance(robotAgent, yellowAgent):
        color = "tab:orange"
    elif isinstance(robotAgent, redAgent):
        color = "tab:red"
    return {"size": size, "color": color}

def wasteAgent_portrayal(wasteAgent):
    size = 5
    if wasteAgent.waste_type == "green":
        color = "lightgreen"
    elif wasteAgent.waste_type == "yellow":
        color = "lightyellow"
    elif wasteAgent.waste_type == "red":
        color = "lightcoral"
    return {"size": size, "color": color}

def radioactivityAgent_portrayal(radioactivityAgent):
    """Portrayal for radioactivity agents based on their level."""
    size = 1
    # Color based on radioactivity level
    if radioactivityAgent.radioactivity < 0.33:
        color = "lightgreen"
    elif radioactivityAgent.radioactivity < 0.66:
        color = "lightyellow"
    elif radioactivityAgent.radioactivity < 1:
        color = "lightcoral"
    else:  # Waste Disposal Zone
        color = "purple"
    return {"size": size, "color": color}

def agent_portrayal(agent):
    """General portrayal function that handles all agent types."""
    if isinstance(agent, radioactivityAgent):
        return radioactivityAgent_portrayal(agent)
    elif isinstance(agent, wasteAgent):
        return wasteAgent_portrayal(agent)
    elif isinstance(agent, (greenAgent, yellowAgent, redAgent)):
        return robotAgent_portrayal(agent)
    return {"size": 1, "color": "gray"}

# @solara.component
# def Histogram(model):
#     update_counter.get() # This is required to update the counter
#     # Note: you must initialize a figure using this method instead of
#     # plt.figure(), for thread safety purpose
#     fig = Figure()
#     ax = fig.subplots()
#     wealth_vals = [agent.wealth for agent in model.agents]
#     # Note: you have to use Matplotlib's OOP API instead of plt.hist
#     # because plt.hist is not thread-safe.
#     ax.hist(wealth_vals, bins=10)
#     solara.FigureMatplotlib(fig)

model_params = {
    "n_green_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of green agents:",
        "min": 0,
        "max": 10,
        "step": 1,
    },
    "n_yellow_agents": {
        "type": "SliderInt",
        "value": 1,
        "label": "Number of yellow agents:",
        "min": 0,
        "max": 10,
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
        "max": 10,
        "step": 1,
    },
    "width": {
        "type": "SliderInt",
        "value": 30,
        "label": "Width:",
        "min": 5,
        "max": 100,
        "step": 1,
    },
    "height": {
        "type": "SliderInt",
        "value": 30,
        "label": "Height:",
        "min": 5,
        "max": 100,
        "step": 1,
    }
}

# Create initial model instance
model = Model(n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_waste=1, width=100, height=100)

SpaceGraph = make_space_component(agent_portrayal)
# GiniPlot = make_plot_component("Gini")

#Create the Dashboard
page = SolaraViz(
    model,
    components=[SpaceGraph],
    model_params=model_params,
    name="Radioactive Waste Collection",
)
# This is required to render the visualization in the Jupyter notebook
page
# to start : "solara run server.py"