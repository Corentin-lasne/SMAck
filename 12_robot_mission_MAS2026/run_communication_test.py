"""Readable communication debug runner focused on green/yellow exchanges."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from typing import Any

from model import Model


COLOR_SHORT = {
    "green": "G",
    "yellow": "Y",
    "red": "R",
    None: "?",
}


@dataclass
class MessageEvent:
    step: int
    sender_id: int
    sender_color: str | None
    recipient_id: int
    recipient_color: str | None
    performative: str
    content: dict[str, Any]


class CommunicationTracer:
    """Collect and print compact communication traces during a run."""

    def __init__(self, model: Model, focus_colors: tuple[str, ...], show_payload: bool, max_payload_keys: int):
        self.model = model
        self.focus_colors = set(focus_colors)
        self.show_payload = show_payload
        self.max_payload_keys = max_payload_keys
        self.events: list[MessageEvent] = []
        self.events_by_step: dict[int, list[MessageEvent]] = {}
        self._current_step = -1
        
        # State tracking for blockage detection
        self.agent_state_history: dict[int, dict] = {}  # agent_id -> {step: state}
        self.last_message_step = -1

        self._orig_send_message = model.send_message

    def install(self) -> None:
        def _wrapped_send_message(sender_id: int, recipient_id: int, performative: str, content: dict[str, Any]) -> None:
            sender = self.model.agent_index_by_id.get(sender_id)
            recipient = self.model.agent_index_by_id.get(recipient_id)
            sender_color = getattr(sender, "team_color", None)
            recipient_color = getattr(recipient, "team_color", None)

            event = MessageEvent(
                step=self._current_step,
                sender_id=sender_id,
                sender_color=sender_color,
                recipient_id=recipient_id,
                recipient_color=recipient_color,
                performative=performative,
                content=content or {},
            )
            self.events.append(event)
            self.events_by_step.setdefault(self._current_step, []).append(event)
            self._orig_send_message(sender_id, recipient_id, performative, content)

        self.model.send_message = _wrapped_send_message  # type: ignore[method-assign]

    def begin_step(self, step: int) -> None:
        self._current_step = step
        self.events_by_step.setdefault(step, [])

    def _pending_counts(self) -> tuple[int, int]:
        pending_green = 0
        pending_yellow = 0
        for robot in self.model.robotAgents:
            pending_count = len(getattr(robot, "pending_messages", []) or [])
            if getattr(robot, "pending_message", None) is not None:
                pending_count += 1
            color = getattr(robot, "team_color", None)
            if color == "green":
                pending_green += pending_count
            elif color == "yellow":
                pending_yellow += pending_count
        return pending_green, pending_yellow

    def _assigned_snapshot(self) -> str:
        pairs = []
        for robot in self.model.robotAgents:
            assigned = getattr(robot, "assigned_waste_id", None)
            if assigned is not None:
                pairs.append(f"A{robot.agent_id}->W{assigned}")
        if not pairs:
            return "none"
        return ", ".join(sorted(pairs))

    def _capture_agent_state(self) -> None:
        """Capture inventory, assignments, locks for all agents."""
        for robot in self.model.robotAgents:
            agent_id = robot.agent_id
            if agent_id not in self.agent_state_history:
                self.agent_state_history[agent_id] = {}
            
            inv_types = [w.waste_type for w in robot.inventory]
            inv_ids = [getattr(w, "waste_id", None) for w in robot.inventory]
            
            state = {
                "step": self._current_step,
                "pos": robot.pos,
                "inventory_types": inv_types,
                "inventory_ids": inv_ids,
                "assigned_waste_id": getattr(robot, "assigned_waste_id", None),
                "assigned_waste_pos": getattr(robot, "assigned_waste_pos", None),
                "locked_waste_ids": set(getattr(robot, "locked_waste_ids", set())),
                "color": getattr(robot, "team_color", None),
            }
            self.agent_state_history[agent_id][self._current_step] = state

    def _detect_stalled_agents(self, min_steps: int = 30) -> list[str]:
        """Detect agents that have had assignment for N steps without progressing."""
        stalled = []
        for robot in self.model.robotAgents:
            assigned = getattr(robot, "assigned_waste_id", None)
            if assigned is None:
                continue
            
            agent_id = robot.agent_id
            assigned_pos = getattr(robot, "assigned_waste_pos", None)
            current_pos = robot.pos
            inv_ids = [getattr(w, "waste_id", None) for w in robot.inventory]
            
            # Check: does agent have the assigned waste?
            if assigned in inv_ids:
                continue  # Already carrying it
            
            # How long has it been assigned?
            history = self.agent_state_history.get(agent_id, {})
            steps_with_assignment = sum(
                1 for s in history.values()
                if s.get("assigned_waste_id") == assigned
            )
            
            if steps_with_assignment >= min_steps:
                stalled.append(
                    f"A{agent_id}({getattr(robot, 'team_color', '?')}) "
                    f"assigned->W{assigned} for {steps_with_assignment} steps, "
                    f"pos={current_pos}, assigned_pos={assigned_pos}, "
                    f"inv={inv_ids}, locked={getattr(robot, 'locked_waste_ids', set())}"
                )
        
        return stalled

    def _detect_universal_locks(self) -> list[str]:
        """Detect waste IDs that are locked by all agents of a color."""
        locks_by_color: dict[str, dict] = {}
        
        for robot in self.model.robotAgents:
            color = getattr(robot, "team_color", None)
            if color not in locks_by_color:
                locks_by_color[color] = {}
            
            for waste_id in getattr(robot, "locked_waste_ids", set()):
                if waste_id not in locks_by_color[color]:
                    locks_by_color[color][waste_id] = []
                locks_by_color[color][waste_id].append(robot.agent_id)
        
        issues = []
        for color, waste_locks in locks_by_color.items():
            color_agents_count = sum(
                1 for r in self.model.robotAgents 
                if getattr(r, "team_color", None) == color
            )
            
            for waste_id, agent_list in waste_locks.items():
                if len(agent_list) == color_agents_count:
                    issues.append(
                        f"UNIVERSAL LOCK: W{waste_id} locked by ALL {color} agents "
                        f"({color_agents_count}): {agent_list}"
                    )
        
        return issues

    def _filtered_step_events(self, step: int) -> list[MessageEvent]:
        events = self.events_by_step.get(step, [])
        return [
            e
            for e in events
            if e.sender_color in self.focus_colors and e.recipient_color in self.focus_colors
        ]

    def print_step(self, step: int, print_empty_steps: bool) -> None:
        filtered = self._filtered_step_events(step)
        
        # Capture state every step for analysis
        self._capture_agent_state()
        
        if filtered:
            self.last_message_step = step
        
        if not filtered and not print_empty_steps:
            return

        pair_counter = Counter(
            f"{COLOR_SHORT.get(e.sender_color)}->{COLOR_SHORT.get(e.recipient_color)}" for e in filtered
        )
        counts_summary = " ".join(f"{k}:{v}" for k, v in sorted(pair_counter.items())) or "none"
        pending_green, pending_yellow = self._pending_counts()
        assigned = self._assigned_snapshot()

        print(
            f"step={step:04d} msgs={counts_summary} pending(G/Y)={pending_green}/{pending_yellow} assigned={assigned}"
        )

        for event in filtered:
            base = (
                f"  - {COLOR_SHORT.get(event.sender_color)}{event.sender_id} -> "
                f"{COLOR_SHORT.get(event.recipient_color)}{event.recipient_id} "
                f"perf={event.performative}"
            )
            if self.show_payload:
                keys = sorted(event.content.keys())[: self.max_payload_keys]
                payload_preview = {k: event.content.get(k) for k in keys}
                print(f"{base} payload={payload_preview}")
            else:
                print(base)

    def print_summary(self) -> None:
        filtered = [
            e
            for e in self.events
            if e.sender_color in self.focus_colors and e.recipient_color in self.focus_colors
        ]
        pair_counter = Counter(
            f"{COLOR_SHORT.get(e.sender_color)}->{COLOR_SHORT.get(e.recipient_color)}" for e in filtered
        )

        print("\n=== Communication summary (focus colors only) ===")
        print(f"total_messages={len(filtered)}")
        print(f"last_message_at_step={self.last_message_step}")
        if not pair_counter:
            print("pairs: none")
            print("hint: no green/yellow protocol seems to emit messages in this branch.")
            return

        for pair, count in sorted(pair_counter.items()):
            print(f"pairs {pair}: {count}")
        
        # ========== BLOCKAGE DIAGNOSTICS ==========
        print("\n=== BLOCKAGE DIAGNOSTICS ===")
        
        # 1. Stalled agents (have assignment but can't acquire it)
        print("\n[1] STALLED AGENTS (assigned but not progressing):")
        stalled = self._detect_stalled_agents(min_steps=30)
        if stalled:
            for msg in stalled:
                print(f"  ⚠️  {msg}")
        else:
            print("  ✓ None detected")
        
        # 2. Universal locks (all agents of a color locked on same waste)
        print("\n[2] UNIVERSAL LOCKS (all agents locked on same waste_id):")
        universal_locks = self._detect_universal_locks()
        if universal_locks:
            for msg in universal_locks:
                print(f"  ⚠️  {msg}")
        else:
            print("  ✓ None detected")
        
        # 3. Agents with inventory but no assignment (should be blocked from pickup by refractory)
        print("\n[3] AGENTS CARRYING WITHOUT ASSIGNMENT (potential drop issues):")
        carrying_unassigned = []
        for robot in self.model.robotAgents:
            if not robot.inventory:
                continue
            assigned = getattr(robot, "assigned_waste_id", None)
            if assigned is not None:
                continue  # Has assignment, ok
            
            inv_types = [w.waste_type for w in robot.inventory]
            inv_ids = [getattr(w, "waste_id", None) for w in robot.inventory]
            carrying_unassigned.append(
                f"A{robot.agent_id}({getattr(robot, 'team_color', '?')}) "
                f"carrying {inv_types} (ids={inv_ids}), no assignment"
            )
        
        if carrying_unassigned:
            for msg in carrying_unassigned:
                print(f"  ⚠️  {msg}")
        else:
            print("  ✓ None detected")
        
        # 4. Current assignments snapshot
        print("\n[4] CURRENT ASSIGNMENTS:")
        current_assignments = []
        for robot in self.model.robotAgents:
            assigned = getattr(robot, "assigned_waste_id", None)
            if assigned is None:
                continue
            
            inv_ids = [getattr(w, "waste_id", None) for w in robot.inventory]
            status = "✓ IN_INVENTORY" if assigned in inv_ids else "⏳ PENDING"
            current_assignments.append(
                f"A{robot.agent_id}({getattr(robot, 'team_color', '?')}) "
                f"assigned->W{assigned} {status} pos={robot.pos}"
            )
        
        if current_assignments:
            for msg in current_assignments:
                print(f"  {msg}")
        else:
            print("  ✓ No active assignments")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compact communication debugger for green/yellow agents")
    parser.add_argument("--steps", type=int, default=1000, help="Maximum number of simulation steps")
    parser.add_argument("--seed", type=int, default=8, help="Random seed for deterministic run")
    parser.add_argument("--width", type=int, default=30)
    parser.add_argument("--height", type=int, default=30)

    parser.add_argument("--green-agents", type=int, default=5)
    parser.add_argument("--yellow-agents", type=int, default=6)
    parser.add_argument("--red-agents", type=int, default=8)

    parser.add_argument("--green-waste", type=int, default=15)
    parser.add_argument("--yellow-waste", type=int, default=15)
    parser.add_argument("--red-waste", type=int, default=15)

    parser.add_argument(
        "--focus-colors",
        default="green,yellow,red",
        help="Comma-separated colors to focus in logs (default: green,yellow,red)",
    )
    parser.add_argument(
        "--print-empty-steps",
        action="store_true",
        help="Also print steps with no focused messages",
    )
    parser.add_argument(
        "--show-payload",
        action="store_true",
        help="Print a compact preview of message payload keys/values",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    focus_colors = tuple(c.strip() for c in args.focus_colors.split(",") if c.strip())

    model = Model(
        n_green_agents=args.green_agents,
        n_yellow_agents=args.yellow_agents,
        n_red_agents=args.red_agents,
        n_green_waste=args.green_waste,
        n_yellow_waste=args.yellow_waste,
        n_red_waste=args.red_waste,
        width=args.width,
        height=args.height,
        seed=args.seed,
    )

    tracer = CommunicationTracer(
        model=model,
        focus_colors=focus_colors,
        show_payload=args.show_payload,
        max_payload_keys=5,
    )
    tracer.install()

    print("=== run_communication start ===")
    print(
        "config: "
        f"seed={args.seed} steps={args.steps} "
        f"agents(G/Y/R)={args.green_agents}/{args.yellow_agents}/{args.red_agents} "
        f"waste(G/Y/R)={args.green_waste}/{args.yellow_waste}/{args.red_waste} "
        f"grid={args.width}x{args.height}"
    )

    for step in range(args.steps):
        if not model.running:
            print(f"stopped: model not running at step={step}")
            break
        tracer.begin_step(step)
        model.step()
        tracer.print_step(step, print_empty_steps=args.print_empty_steps)

    tracer.print_summary()


if __name__ == "__main__":
    main()
