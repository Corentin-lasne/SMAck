""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent
import random

class baseAgent(Agent):
    def __init__(self, model):
        super().__init__(model)

        self.knowledge = {
            "observations": [],
            "actions": [],
        }

        self.percepts = {}

    def step(self):
        self.step_agent()

    def step_agent(self):
        self.update(self.knowledge, self.percepts)
        action = self.deliberate(self.knowledge)
        percepts = self.model.do(action)

    def update(self, knowledge, percepts):
        pass

    @staticmethod
    def deliberate(knowledge):
        actions = {
            "move_up": 0,
            "move_down": 1,
            "move_right": 2,
            "move_left": 3,
            "pick_up": 4,
            "drop": 5,
        }
        return random.choice(list(actions.values()))


class greenAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1"]
        self.target_waste = "g"
        self.max_capacity = 2
    
class yellowAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1", "z2"]
        self.target_waste = "y"
        self.max_capacity = 2

class redAgent(baseAgent):
    def __init__(self, model):
        super().__init__(model)

        self.allowed_zones = ["z1", "z2", "z3"]
        self.target_waste = "r"
        self.max_capacity = 1
