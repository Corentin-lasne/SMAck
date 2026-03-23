"""Configuration constants for action encoding and waste transformation rules.

Contains:
- `actions`: discrete action IDs used by the simulation environment
- `WASTE_UPGRADE`: conversion mapping for transform operations
"""

actions = {
        "move_up": 0,
        "move_down": 1,
        "move_right": 2,
        "move_left": 3,
        "pick_up": 4,
        "drop": 5,
        "transform": 6,
        "send_message": 7
        }

WASTE_UPGRADE = {"green": "yellow", "yellow": "red"}