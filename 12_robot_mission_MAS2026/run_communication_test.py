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

    def _filtered_step_events(self, step: int) -> list[MessageEvent]:
        events = self.events_by_step.get(step, [])
        return [
            e
            for e in events
            if e.sender_color in self.focus_colors and e.recipient_color in self.focus_colors
        ]

    def print_step(self, step: int, print_empty_steps: bool) -> None:
        filtered = self._filtered_step_events(step)
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
        if not pair_counter:
            print("pairs: none")
            print("hint: no green/yellow protocol seems to emit messages in this branch.")
            return

        for pair, count in sorted(pair_counter.items()):
            print(f"pairs {pair}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compact communication debugger for green/yellow agents")
    parser.add_argument("--steps", type=int, default=150, help="Maximum number of simulation steps")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic run")
    parser.add_argument("--width", type=int, default=30)
    parser.add_argument("--height", type=int, default=30)

    parser.add_argument("--green-agents", type=int, default=4)
    parser.add_argument("--yellow-agents", type=int, default=3)
    parser.add_argument("--red-agents", type=int, default=1)

    parser.add_argument("--green-waste", type=int, default=12)
    parser.add_argument("--yellow-waste", type=int, default=8)
    parser.add_argument("--red-waste", type=int, default=2)

    parser.add_argument(
        "--focus-colors",
        default="green,yellow",
        help="Comma-separated colors to focus in logs (default: green,yellow)",
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
