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
    def __init__(self, n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_waste=1, width=100, height=100, seed=None):
        """Initialize the model.

        Args:
            n_green_agents (int, optional): Number of green agents. Defaults to 1.
            n_yellow_agents (int, optional): Number of yellow agents. Defaults to 1.
            n_red_agents (int, optional): Number of red agents. Defaults to 1.
            n_waste (int, optional): Number of waste items. Defaults to 1.
            width (int, optional): Grid width. Defaults to 100.
            height (int, optional): Grid height. Defaults to 100.
            seed (int, optional): Random seed. Defaults to None.
        """
        super().__init__(seed=seed)
        self.num_green_agents = n_green_agents
        self.num_yellow_agents = n_yellow_agents
        self.num_red_agents = n_red_agents
        self.num_waste = n_waste
        self.grid = MultiGrid(width, height, torus=False)
        self.robotAgents = []
        
        # Define z1, z2, z3 as third area of the grid
        self.z1 = (0, 0, width//3, height)
        self.z2 = (width//3, 0, 2*width//3, height)
        self.z3 = (2*width//3, 0, width, height)

        # Create the Waste Disposal Zone at the very right of the grid, at random y position
        waste_disposal_zone_y = self.random.randrange(0, height)
        self.grid.place_agent(radioactivityAgent(self, 4), (width-1, waste_disposal_zone_y))

        # Attribute corresponding radioactivity agents to each area cell
        for x in range(self.z1[0], self.z1[2]):
            for y in range(self.z1[1], self.z1[3]):
                self.grid.place_agent(radioactivityAgent(self, 1), (x, y))
        
        for x in range(self.z2[0], self.z2[2]):
            for y in range(self.z2[1], self.z2[3]):
                self.grid.place_agent(radioactivityAgent(self, 2), (x, y))
        
        for x in range(self.z3[0], self.z3[2]):
            for y in range(self.z3[1], self.z3[3]):
                if (x, y) != (width-1, waste_disposal_zone_y):  # Avoid placing a radioactivity agent on the Waste Disposal Zone
                    self.grid.place_agent(radioactivityAgent(self, 3), (x, y))

        # Create waste agents and place them randomly in the area 1
        for i in range(self.num_waste):
            x = self.random.randrange(self.z1[0], self.z1[2])
            y = self.random.randrange(self.z1[1], self.z1[3])
            self.grid.place_agent(wasteAgent(self, "green"), (x, y))

        # Create agents and place them randomly in their area
        for i in range(self.num_green_agents):
            green_agent = greenAgent(self)
            self.robotAgents.append(green_agent)
            x = self.random.randrange(self.z1[0], self.z1[2])
            y = self.random.randrange(self.z1[1], self.z1[3])
            self.grid.place_agent(green_agent, (x, y))
            
        for i in range(self.num_yellow_agents):
            yellow_agent = yellowAgent(self)
            self.robotAgents.append(yellow_agent)
            x = self.random.randrange(self.z2[0], self.z2[2])
            y = self.random.randrange(self.z2[1], self.z2[3])
            self.grid.place_agent(yellow_agent, (x, y))
            
        for i in range(self.num_red_agents):
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
        x, y = agent.pos
        if direction == "up":
            new_pos = (x, y + 1)
        elif direction == "down":
            new_pos = (x, y - 1)
        elif direction == "left":
            new_pos = (x - 1, y)
        elif direction == "right":
            new_pos = (x + 1, y)
        else:
            raise ValueError(f"Unknown direction: {direction}")

        # Check if the new position is within the grid bounds
        if self.grid.out_of_bounds(new_pos):
            return self.get_percepts(agent)  # Return current percepts if move is invalid

        # Move the agent to the new position
        self.grid.move_agent(agent, new_pos)
        return self.get_percepts(agent)

    def pick_up(self, agent):
        """Pick up waste if the agent is on a cell with waste and return the resulting percepts."""
        cell_contents = self.grid.get_cell_list_contents([agent.pos])
        for obj in cell_contents:
            if isinstance(obj, wasteAgent) and len(agent.inventory) < agent.max_capacity:
                agent.inventory.append(obj)
                self.grid.remove_agent(obj)
                break
        return self.get_percepts(agent)

    def drop(self, agent):
        """Drop waste if the agent is carrying waste and return the resulting percepts."""
        if agent.inventory:
            waste = agent.inventory.pop()
            self.grid.place_agent(waste, agent.pos)
        return self.get_percepts(agent)

    def transform(self, agent):
        """Transform waste if the agent has the required wastes and return the resulting percepts."""
        return self.get_percepts(agent)
    
    def get_percepts(self, agent):
        """Get percepts for an agent (its current position and surroundings)."""
        percepts = {"position": agent.pos, "surrounding": {}}
        if agent.pos:
            neighborhood = self.grid.get_neighborhood(agent.pos, include_center=True)
            for pos in neighborhood:
                percepts["surrounding"][pos] = self.grid.get_cell_list_contents([pos])
        return percepts