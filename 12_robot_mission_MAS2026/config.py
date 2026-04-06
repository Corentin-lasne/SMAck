actions = {
        "move_up": 0,
        "move_down": 1,
        "move_right": 2,
        "move_left": 3,
        "pick_up": 4,
        "drop": 5,
        "transform": 6,
        "send_message": 7,
        }

WASTE_UPGRADE = {"green": "yellow", "yellow": "red"}

# Shared defaults used by both batch runner and Solara dashboard.
DEFAULT_MODEL_PARAMS = {
        "n_green_agents": 8,
        "n_yellow_agents": 12,
        "n_red_agents": 13,
        "n_green_waste": 15,
        "n_yellow_waste": 14,
        "n_red_waste": 13,
        "width": 25,
        "height": 25,
}