""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Model
from mesa.space import MultiGrid
from agents import greenAgent, yellowAgent, redAgent
from objects import radioactivityAgent, wasteAgent

class Model(Model):
    """A model with some number of agents, number of waste, and a grid cell."""
    def __init__(self, n_agents=[1,1,1], n_waste=1, width=100, height=100, seed=None):
        """Initialize the model.

        Args:
            n_agents (int, optional): Number of agents. Defaults to 1.
            n_waste (int, optional): Number of waste items. Defaults to 1.
            width (int, optional): Grid width. Defaults to 100.
            height (int, optional): Grid height. Defaults to 100.
            seed (int, optional): Random seed. Defaults to None.
        """
        super().__init__(seed=seed)
        self.num_agents = n_agents
        self.num_waste = n_waste
        self.grid = MultiGrid(width, height, torus=False)
        self.robotAgents = []
        
        # Define z1, z2, z3 as third area of the grid
        self.z3 = (0, 0, width//3, height)
        self.z2 = (width//3, 0, 2*width//3, height)
        self.z1 = (2*width//3, 0, width, height)
        
        # Attribute corresponding radioactivity agents to each area cell
        for x in range(self.z1[0], self.z1[2]):
            for y in range(self.z1[1], self.z1[3]):
                self.grid.place_agent(radioactivityAgent(self, 1), (x, y))
        
        for x in range(self.z2[0], self.z2[2]):
            for y in range(self.z2[1], self.z2[3]):
                self.grid.place_agent(radioactivityAgent(self, 2), (x, y))
        
        for x in range(self.z3[0], self.z3[2]):
            for y in range(self.z3[1], self.z3[3]):
                self.grid.place_agent(radioactivityAgent(self, 3), (x, y))

        # Create waste agents and place them randomly in the area 1
        for i in range(self.num_waste):
            x = self.random.randrange(self.z1[0], self.z1[2])
            y = self.random.randrange(self.z1[1], self.z1[3])
            self.grid.place_agent(wasteAgent(self, "green"), (x, y))

        # Create agents and place them randomly in their area
        for i in range(self.num_agents[0]):
            green_agent = greenAgent(self)
            self.robotAgents.append(green_agent)
            x = self.random.randrange(self.z1[0], self.z1[2])
            y = self.random.randrange(self.z1[1], self.z1[3])
            self.grid.place_agent(green_agent, (x, y))
            
        for i in range(self.num_agents[1]):
            yellow_agent = yellowAgent(self)
            self.robotAgents.append(yellow_agent)
            x = self.random.randrange(self.z2[0], self.z2[2])
            y = self.random.randrange(self.z2[1], self.z2[3])
            self.grid.place_agent(yellow_agent, (x, y))
            
        for i in range(self.num_agents[2]):
            red_agent = redAgent(self)
            self.robotAgents.append(red_agent)
            x = self.random.randrange(self.z3[0], self.z3[2])
            y = self.random.randrange(self.z3[1], self.z3[3])
            self.grid.place_agent(red_agent, (x, y))
        
    def step(self):
        agent_list = list(self.robotAgents)
        self.random.shuffle(agent_list)
        for agent in agent_list:
            agent.step_agent()

    def do(self, agent, action):
        """Execute the given action for the specified agent and returns the resulting percepts."""
        if action.startswith("move"):
            direction = action.split("_")[1]
            return self.move_agent(agent, direction)
        elif action == "pick_up":
            return self.pick_up(agent)
        elif action == "drop":
            return self.drop(agent)
        elif action == "transform":
            return self.transform(agent)
        else:
            raise ValueError(f"Unknown action: {action}")
        
    def move_agent(self, agent, direction):
        """Move the agent in the specified direction and return the resulting percepts.
        """
        pass

    def pick_up(self, agent):
        """Pick up waste if the agent is on a cell with waste and return the resulting percepts."""
        pass

    def drop(self, agent):
        """Drop waste if the agent is carrying waste and return the resulting percepts."""
        pass

    def transform(self, agent):
        """Transform waste if the agent has the required wastes and return the resulting percepts."""
        pass

