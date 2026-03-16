""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent

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
        self.update(self.knowledge, self.percepts, self.action)
        action = deliberate(self.knowledge)
        percepts = self.model.do(action)

    def update(self, knowledge, percepts, action):
        pass

    def deliberate(knowledge):



    
        
    

class greenAgent(baseAgent):
    
class yellowAgent(baseAgent):

class redAgent(baseAgent):
