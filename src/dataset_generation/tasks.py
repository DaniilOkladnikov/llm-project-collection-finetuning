"""All Tasks.md entries transcribed into executable :class:`TaskSpec` s.

Each program is in DSL block form (one branching per step). Early-exit guards are
single-arm ``when`` steps with no ``otherwise`` — they fall through (cursor
advances) when the guard is false (DSL §5.3). Cross-step values use ``remember``
(turn-scoped memory); within-step values use ``temp``. Answer wording follows
Tasks.md; obvious logic typos there are corrected while keeping the wording.
"""

from __future__ import annotations

from typing import List

from finetuning.models import VariableDefinition, VariableType, LocationMode

from .helpers import (
    ATypeIn, ATypeInNotIn, ATypeSharedBy, BinOp, Count, FirstEmpty, FirstEmptyIn,
    FirstHolding, FirstHoldingIn, FirstHoldingNotIn, FirstOccupiedIn, Held,
    IsNone, IsNotNone, ListExpr, LocationsHolding, MemRef, MemTrue, Not, NumberLit,
    Position, TempRef, TypeOf,
    at_home, contains_only, first_empty_location_exists, first_holding_exists,
    gripper_is, has, has_no, holding, holding_anything, is_empty, is_full,
    is_not_empty, more_empty_room, no_location_holds, same_count,
)
from .program import (
    Answer, ApproachObserve, ApproachPick, CheckGripper, CheckPosition, GoTo,
    Observe, ObserveEverything, PickFrom, PlaceAt, Program, Remember, Temp,
    branch, linear, otherwise, when,
)
from .taskspec import TaskSpec


# --- variable-definition shorthands ---------------------------------------

def OT(name: str, differ=None) -> VariableDefinition:
    c = {"must_differ_from": differ} if differ else None
    return VariableDefinition(name=name, type=VariableType.OBJECT_TYPE, constraints=c)


def LOC(name: str, mode: LocationMode = LocationMode.ANY, differ=None) -> VariableDefinition:
    c = {"must_differ_from": differ} if differ else None
    return VariableDefinition(name=name, type=VariableType.LOCATION, mode=mode, constraints=c)


X, W = TypeOf("X"), TypeOf("W")

TASKS: List[TaskSpec] = []


def task(spec: TaskSpec) -> TaskSpec:
    TASKS.append(spec)
    return spec


# ============================ pick ======================================

task(TaskSpec(
    id="pick_X_from_A", header="Pick up $X from $A", intent="pick",
    variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.X} from {e.t('loc')}.",
        "answer_3": lambda e: f"There is no {e.X} in {e.A}.",
    },
))

task(TaskSpec(
    id="pick_whatever_in_A", header="Pick up whatever is in $A", intent="pick",
    variables=[LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstOccupiedIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: f"There is nothing in {e.A}.",
    },
))

task(TaskSpec(
    id="pick_in_A_else_B", header="Pick up whatever is in $A. If $A is empty, pick from $B instead.",
    intent="pick", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               pre=[Temp("loc", FirstOccupiedIn(["A"]))]),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstOccupiedIn(["B"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_4": lambda e: f"Both {e.A} and {e.B} are empty.",
    },
))

task(TaskSpec(
    id="pick_X_or_W_from_A", header="Pick up $X or $W from $A, whichever is there.",
    intent="pick", variables=[OT("$X"), OT("$W", differ="$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("locX"), PickFrom(TempRef("locX")), Answer("answer_2")),
               when(IsNotNone("locW"), PickFrom(TempRef("locW")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("locX", FirstHoldingIn(["A"], X)),
                    Temp("locW", FirstHoldingIn(["A"], W))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('locX')}.",
        "answer_3": lambda e: f"Picked {e.held} from {e.t('locW')}.",
        "answer_4": lambda e: f"There is no {e.X} or {e.W} in {e.A}.",
    },
))

task(TaskSpec(
    id="pick_not_W_from_A", header="Pick up whatever is at $A, as long as it is not a $W",
    intent="pick", variables=[OT("$W"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingNotIn(["A"], [W]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: (f"{e.A} is empty" if e.is_empty("A")
                               else f"There is nothing except {e.W} in {e.A}"),
    },
))

task(TaskSpec(
    id="get_X_return", header="Get $X from $A and come back to where you started",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckPosition(), Remember("start_position", Position()), CheckGripper(),
               Observe(["A"])),
        branch(when(gripper_is("closed"), Answer("answer_1"))),
        branch(when(IsNotNone("loc"),
                    PickFrom(TempRef("loc")), GoTo(MemRef("start_position")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')} and returned to {e.m('start_position')}.",
        "answer_3": lambda e: f"There is no {e.X} in {e.A}",
    },
))

task(TaskSpec(
    id="go_see_pick_X_return", header="Go to $A, see what's there, pick it up if it's $X, then come back.",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckPosition(), Remember("start_position", Position()), CheckGripper(),
               Observe(["A"])),
        branch(when(gripper_is("closed"), Answer("answer_1"))),
        branch(when(IsNotNone("loc"), PickFrom(MemRef("loc"))),
               pre=[Remember("loc", FirstHoldingIn(["A"], X))]),
        linear(GoTo(MemRef("start_position")), Answer("answer_2")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: (
            f"Picked {e.held} from {e.m('loc')} and returned to {e.m('start_position')}."
            if e.m("loc") is not None
            else f"There is no {e.X} in {e.A}, returned to {e.m('start_position')}"),
    },
))

task(TaskSpec(
    id="pick_whatever_return", header="Pick up whatever is in $A and bring it back.",
    intent="pick", variables=[LOC("$A")],
    program=Program([
        linear(CheckPosition(), Remember("start_position", Position()), CheckGripper(),
               Observe(["A"])),
        branch(when(gripper_is("closed"), Answer("answer_1"))),
        branch(when(IsNotNone("loc"), PickFrom(MemRef("loc"))),
               pre=[Remember("loc", FirstOccupiedIn(["A"]))]),
        linear(GoTo(MemRef("start_position")), Answer("answer_2")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: (
            f"Picked {e.held} from {e.m('loc')} and returned to {e.m('start_position')}."
            if e.m("loc") is not None
            else f"There is nothing in {e.A}, returned to {e.m('start_position')}"),
    },
))

task(TaskSpec(
    id="find_and_pick_X", header="Find and pick up an $X", intent="pick",
    variables=[OT("$X")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(ObserveEverything())),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHolding(X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Found and picked {e.X} from {e.t('loc')}.",
        "answer_3": lambda e: f"I could not find an {e.X} anywhere.",
    },
))

task(TaskSpec(
    id="check_A_pick_X_or_report", header="Check what is at $A; if there is an $X pick it, otherwise tell me what is there",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(is_empty("A"), Answer("answer_2"))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.A} is empty.",
        "answer_3": lambda e: f"Picked {e.X} from {e.t('loc')}.",
        "answer_4": lambda e: f"There is no {e.X} at {e.A}. {e.A} contains: {e.desc('A')}.",
    },
))

task(TaskSpec(
    id="pick_if_X_else_home", header="If $A has an $X, pick it; otherwise go home",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(GoTo("home"), Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.X} from {e.t('loc')}.",
        "answer_3": lambda e: f"There is no {e.X} in {e.A} — went home.",
    },
))

task(TaskSpec(
    id="pick_not_X_from_A", header="Pick up an object at $A that is not an $X",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingNotIn(["A"], [X]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: f"{e.A} has only {e.X} or is empty — nothing else to pick.",
    },
))

task(TaskSpec(
    id="pick_only_object", header="Pick the only object in $A", intent="pick",
    variables=[LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(BinOp("==", Count("A"), NumberLit(1)),
                    PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstOccupiedIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: f"{e.A} does not have exactly one object.",
    },
))

task(TaskSpec(
    id="pick_match_B", header="Pick from $A the same kind of object that is in $B",
    intent="pick", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(is_empty("B"), Answer("answer_2"))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstHoldingIn(["A"], ATypeIn("B")))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.B} is empty — there is no reference object.",
        "answer_3": lambda e: f"Picked {e.held} from {e.t('loc')} (matching what is in {e.B}).",
        "answer_4": lambda e: f"{e.A} has nothing of the kind found in {e.B}.",
    },
))

task(TaskSpec(
    id="pick_shared_with_B", header="Pick from $A something that is also present in $B",
    intent="pick", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("t"), Answer("answer_2")),
               pre=[Remember("t", ATypeSharedBy("A", "B"))]),
        linear(PickFrom(FirstHoldingIn(["A"], MemRef("t"))), Answer("answer_3")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.A} and {e.B} share no object type.",
        "answer_3": lambda e: f"Picked {e.held} from {e.last_pick}.",
    },
))

task(TaskSpec(
    id="pick_not_in_B", header="Pick from $A something that is not present in $B",
    intent="pick", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("t"), Answer("answer_2")),
               pre=[Remember("t", ATypeInNotIn("A", "B"))]),
        linear(PickFrom(FirstHoldingIn(["A"], MemRef("t"))), Answer("answer_3")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Every type in {e.A} is also in {e.B}.",
        "answer_3": lambda e: f"Picked {e.held} from {e.last_pick}.",
    },
    notes="pick_not_in_B",
))

task(TaskSpec(
    id="pick_A_or_B_has_X", header="Check $A and $B; pick the $X from whichever has it",
    intent="pick", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstHoldingIn(["B"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.X} from {e.t('loc')} in {e.A}.",
        "answer_3": lambda e: f"Picked {e.X} from {e.t('loc')} in {e.B}.",
        "answer_4": lambda e: f"Neither {e.A} nor {e.B} has an {e.X}.",
    },
))

task(TaskSpec(
    id="pick_A_or_B_nonempty", header="Check $A and $B; pick from whichever is not empty",
    intent="pick", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               pre=[Temp("loc", FirstOccupiedIn(["A"]))]),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstOccupiedIn(["B"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')} in {e.A}.",
        "answer_3": lambda e: f"Picked {e.held} from {e.t('loc')} in {e.B}.",
        "answer_4": lambda e: f"Both {e.A} and {e.B} are empty.",
    },
))

task(TaskSpec(
    id="pick_if_at_least_N", header="Pick from $A only if $A has at least 2 objects",
    intent="pick", variables=[LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(BinOp(">=", Count("A"), NumberLit(2)),
                    PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstOccupiedIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.held} from {e.t('loc')}.",
        "answer_3": lambda e: f"{e.A} has fewer than 2 objects.",
    },
))

task(TaskSpec(
    id="pick_if_only_X", header="Pick from $A only if everything there is an $X",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(is_empty("A"), Answer("answer_2"))),
        branch(when(contains_only("A", X), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.A} is empty.",
        "answer_3": lambda e: f"Picked {e.X} from {e.t('loc')}.",
        "answer_4": lambda e: f"{e.A} contains something other than {e.X}.",
    },
))

task(TaskSpec(
    id="if_A_has_X_pick_B", header="Check $A; if it has an $X, pick something from $B",
    intent="pick", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(has_no("A", X), Answer("answer_2"))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_3")),
               otherwise(Answer("answer_4")),
               pre=[Temp("loc", FirstOccupiedIn(["B"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.A} has no {e.X}.",
        "answer_3": lambda e: f"{e.A} has an {e.X}, so I picked {e.held} from {e.t('loc')} in {e.B}.",
        "answer_4": lambda e: f"{e.A} has an {e.X}, but {e.B} is empty.",
    },
))

task(TaskSpec(
    id="pick_X_report_rest", header="Pick $X from $A, then tell me what $A has left",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"Picked {e.X} from {e.t('loc')}. {e.A} still has: {e.desc('A')}.",
        "answer_3": lambda e: f"There is no {e.X} in {e.A}.",
    },
))

task(TaskSpec(
    id="report_then_pick_X", header="Tell me what is at $A, then pick up the $X from there",
    intent="pick", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        linear(Remember("snapshot", ListExpr("occupied", "A"))),
        branch(when(IsNotNone("loc"), PickFrom(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstHoldingIn(["A"], X))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — can't pick.",
        "answer_2": lambda e: f"{e.A} contained {e.join(e.m('snapshot'))}. Picked {e.X} from {e.t('loc')}.",
        "answer_3": lambda e: f"{e.A} contains {e.join(e.m('snapshot'))}. There is no {e.X}.",
    },
))


# ============================ place =====================================

task(TaskSpec(
    id="place_X_into_A", header="You are holding $X. Place it into $A", intent="place",
    held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(Answer("answer_2")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} in {e.A}.",
        "answer_2": lambda e: f"There is no empty space in {e.A}.",
    },
))

task(TaskSpec(
    id="place_what_holding_at_A", header="Place what you are holding at $A", intent="place",
    held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(Answer("answer_2")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} in {e.A}.",
        "answer_2": lambda e: f"There is no empty space in {e.A}.",
    },
))

task(TaskSpec(
    id="place_X_somewhere", header="Place $X somewhere.", intent="place",
    held="X", variables=[OT("$X")],
    program=Program([
        linear(ObserveEverything()),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(Answer("answer_2")),
               pre=[Temp("loc", FirstEmpty())]),
    ]),
    answers={
        "answer_1": lambda e: f"Successfully placed at {e.t('loc')}",
        "answer_2": lambda e: "Cannot place, no empty space found",
    },
))

task(TaskSpec(
    id="place_prefer_A", header="Place $X, preferring $A. If $A is full, find any empty spot",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(ObserveEverything()),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstEmpty())]),
    ]),
    answers={
        "answer_1": lambda e: f"Successfully placed at {e.t('loc')}",
        "answer_2": lambda e: f"Successfully placed at {e.t('loc')}",
        "answer_3": lambda e: "Cannot place, no empty space found",
    },
))

task(TaskSpec(
    id="place_at_A_or_anywhere", header="You are holding $X. Put it at $A if possible, otherwise anywhere",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(ObserveEverything()),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstEmpty())]),
    ]),
    answers={
        "answer_1": lambda e: f"Successfully placed at {e.t('loc')}",
        "answer_2": lambda e: f"Successfully placed at {e.t('loc')}",
        "answer_3": lambda e: "Cannot place, no empty space found",
    },
))

task(TaskSpec(
    id="place_not_in_A", header="You are holding $X. Place it somewhere, but not in $A",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(ObserveEverything()),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(Answer("answer_2")),
               pre=[Temp("loc", FirstEmpty(outside=["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.t('loc')}.",
        "answer_2": lambda e: f"There is no empty location outside {e.A}.",
    },
))

task(TaskSpec(
    id="place_A_else_B", header="You are holding $X. Place it at $A, otherwise try $B",
    intent="place", held="X", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(Observe(["A", "B"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
        branch(when(IsNotNone("loc2"), PlaceAt(TempRef("loc2")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc2", FirstEmptyIn(["B"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.t('loc')}.",
        "answer_2": lambda e: f"{e.A} was full, so I placed {e.X} at {e.t('loc2')}.",
        "answer_3": lambda e: f"Both {e.A} and {e.B} are full — still holding {e.X}.",
    },
))

task(TaskSpec(
    id="place_only_if_empty", header="You are holding $X. Place it at $A, only if $A is completely empty",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(is_not_empty("A"), Answer("answer_1"))),
        linear(Temp("loc", FirstEmptyIn(["A"])), PlaceAt(TempRef("loc")), Answer("answer_2")),
    ]),
    answers={
        "answer_1": lambda e: f"{e.A} is not empty — did not place.",
        "answer_2": lambda e: f"{e.A} was empty; placed {e.X} at {e.t('loc')}.",
    },
))

task(TaskSpec(
    id="place_A_else_B_if_W", header="You are holding $X. Place it at $A; if $A has a $W in it, place it at $B instead",
    intent="place", held="X", variables=[OT("$X"), OT("$W", differ="$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(Observe(["A", "B"])),
        branch(when(has("A", W), Remember("dest", FirstEmptyIn(["B"]))),
               otherwise(Remember("dest", FirstEmptyIn(["A"])))),
        branch(when(IsNotNone("dest"), PlaceAt(MemRef("dest")), Answer("answer_1")),
               otherwise(Answer("answer_2"))),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.m('dest')}.",
        "answer_2": lambda e: (
            f"{e.A} has a {e.W} and {e.B} is full — still holding {e.X}."
            if e.has("A", "W")
            else f"{e.A} is full — still holding {e.X}."),
    },
))

task(TaskSpec(
    id="place_more_room", header="You are holding $X. Place it in whichever of $A or $B has more room",
    intent="place", held="X", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(Observe(["A", "B"])),
        branch(when(BinOp("and", is_full("A"), is_full("B")), Answer("answer_1")),
               when(more_empty_room("A", "B"), PlaceAt(FirstEmptyIn(["A"])), Answer("answer_2")),
               otherwise(PlaceAt(FirstEmptyIn(["B"])), Answer("answer_3"))),
    ]),
    answers={
        "answer_1": lambda e: f"Both {e.A} and {e.B} are full — still holding {e.X}.",
        "answer_2": lambda e: f"{e.A} has more room; placed {e.X} at {e.last_place}.",
        "answer_3": lambda e: f"Placed {e.X} at {e.last_place} in {e.B}.",
    },
))

task(TaskSpec(
    id="place_X_to_A_W_to_B", header="You are holding something. If it is an $X place it at $A; if it is a $W place it at $B",
    intent="place", held="any", variables=[OT("$X"), OT("$W", differ="$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        branch(when(holding(X), Observe(["A"])),
               when(holding(W), Observe(["B"])),
               otherwise(Answer("answer_1"))),
        branch(when(holding(X), Temp("loc", FirstEmptyIn(["A"]))),
               when(holding(W), Temp("loc", FirstEmptyIn(["B"])))),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3"))),
    ]),
    answers={
        "answer_1": lambda e: f"I am holding something else — neither an {e.X} nor a {e.W}.",
        "answer_2": lambda e: f"Placed it at {e.t('loc')}.",
        "answer_3": lambda e: (f"{e.A} is full — still holding {e.X}."
                               if e.held == e.binding.type_value("X")
                               else f"{e.B} is full — still holding {e.W}."),
    },
))

task(TaskSpec(
    id="place_then_home", header="You are holding $X. Place it somewhere, then go home",
    intent="place", held="X", variables=[OT("$X")],
    program=Program([
        linear(ObserveEverything()),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), GoTo("home"), Answer("answer_1")),
               otherwise(GoTo("home"), Answer("answer_2")),
               pre=[Temp("loc", FirstEmpty())]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.t('loc')}, then went home.",
        "answer_2": lambda e: f"Found no empty location; went home still holding {e.X}.",
    },
))

task(TaskSpec(
    id="drop_then_home", header="You are holding $X. Drop it somewhere, then go home",
    intent="place", held="X", variables=[OT("$X")],
    program=Program([
        linear(ObserveEverything()),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), GoTo("home"), Answer("answer_1")),
               otherwise(GoTo("home"), Answer("answer_2")),
               pre=[Temp("loc", FirstEmpty())]),
    ]),
    answers={
        "answer_1": lambda e: f"Dropped {e.X} at {e.t('loc')}, then went home.",
        "answer_2": lambda e: f"Found nowhere to drop {e.X}; went home still holding it.",
    },
))

task(TaskSpec(
    id="place_report_full", header="You are holding $X. Place it at $A; report whether $A is then full",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(is_full("A"), Answer("answer_1"))),
        linear(Remember("last", BinOp("==", Count("A", empty=True), NumberLit(1))),
               Remember("loc", FirstEmptyIn(["A"])),
               PlaceAt(MemRef("loc"))),
        branch(when(MemTrue("last"), Answer("answer_2")),
               otherwise(Answer("answer_3"))),
    ]),
    answers={
        "answer_1": lambda e: f"{e.A} is already full — could not place.",
        "answer_2": lambda e: f"Placed {e.X} at {e.m('loc')}; {e.A} is now full.",
        "answer_3": lambda e: f"Placed {e.X} at {e.m('loc')}; {e.A} still has room.",
    },
))

task(TaskSpec(
    id="place_X_keep_if_full", header="You are holding $X. Place it at $A; if $A is full, keep holding it",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_1")),
               otherwise(Answer("answer_2")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.t('loc')}.",
        "answer_2": lambda e: f"{e.A} is full — keeping hold of {e.X}.",
    },
))

task(TaskSpec(
    id="place_unless_has_X", header="You are holding $X. Place it at $A, unless $A already has an $X",
    intent="place", held="X", variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(has("A", X), Answer("answer_1"))),
        branch(when(IsNotNone("loc"), PlaceAt(TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: f"{e.A} already has an {e.X} — did not place.",
        "answer_2": lambda e: f"Placed {e.X} at {e.t('loc')}.",
        "answer_3": lambda e: f"{e.A} is full — still holding {e.X}.",
    },
))

task(TaskSpec(
    id="place_A_else_B_if_has_X", header="You are holding $X. Place it at $A; if $A already has an $X, place it at $B instead",
    intent="place", held="X", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(Observe(["A", "B"])),
        branch(when(has("A", X), Remember("dest", FirstEmptyIn(["B"]))),
               otherwise(Remember("dest", FirstEmptyIn(["A"])))),
        branch(when(IsNotNone("dest"), PlaceAt(MemRef("dest")), Answer("answer_1")),
               otherwise(Answer("answer_2"))),
    ]),
    answers={
        "answer_1": lambda e: f"Placed {e.X} at {e.m('dest')}.",
        "answer_2": lambda e: (
            f"{e.A} already has an {e.X} and {e.B} is full — still holding {e.X}."
            if e.has("A", "X") else f"{e.A} is full — still holding {e.X}."),
    },
))

task(TaskSpec(
    id="place_at_A_or_B_if_X", header="You are holding something. Place it at $A, but if it is an $X place it at $B",
    intent="place", held="any", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(Observe(["A", "B"])),
        branch(when(holding(X), Remember("dest", FirstEmptyIn(["B"]))),
               otherwise(Remember("dest", FirstEmptyIn(["A"])))),
        branch(when(IsNotNone("dest"), PlaceAt(MemRef("dest")), Answer("answer_1")),
               otherwise(Answer("answer_2"))),
    ]),
    answers={
        "answer_1": lambda e: f"Placed it at {e.m('dest')}.",
        "answer_2": lambda e: (f"{e.B} is full — still holding it."
                               if e.held == e.binding.type_value("X")
                               else f"{e.A} is full — still holding it."),
    },
))


# ============================ move ======================================

task(TaskSpec(
    id="move_X_from_A_to_B", header="Move $X from $A to $B", intent="move",
    variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("src"), Answer("answer_2")),
               pre=[Remember("src", FirstHoldingIn(["A"], X))]),
        branch(when(IsNone("dest"), Answer("answer_3")),
               pre=[Remember("dest", FirstEmptyIn(["B"]))]),
        linear(PickFrom(MemRef("src")), PlaceAt(MemRef("dest")), Answer("answer_4")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — free the gripper first.",
        "answer_2": lambda e: f"There is no {e.X} in {e.A}.",
        "answer_3": lambda e: f"{e.B} is full.",
        "answer_4": lambda e: f"Moved {e.X} from {e.m('src')} to {e.m('dest')}.",
    },
))

task(TaskSpec(
    id="move_X_else_back", header="Move $X from $A to $B; if $B is full, put $X back in $A",
    intent="move", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("src"), Answer("answer_2")),
               pre=[Remember("src", FirstHoldingIn(["A"], X))]),
        linear(PickFrom(MemRef("src"))),
        branch(when(IsNotNone("dest"), PlaceAt(MemRef("dest")), Answer("answer_3")),
               otherwise(PlaceAt(MemRef("src")), Answer("answer_4")),
               pre=[Remember("dest", FirstEmptyIn(["B"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — free the gripper first.",
        "answer_2": lambda e: f"There is no {e.X} in {e.A}.",
        "answer_3": lambda e: f"Moved {e.X} from {e.m('src')} to {e.m('dest')}.",
        "answer_4": lambda e: f"{e.B} is full, so I put {e.X} back at {e.m('src')} in {e.A}.",
    },
))

task(TaskSpec(
    id="move_whatever_A_to_B", header="Pick whatever is at $A and place it in $B", intent="move",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("src"), Answer("answer_2")),
               pre=[Remember("src", FirstOccupiedIn(["A"]))]),
        branch(when(IsNone("dest"), Answer("answer_3")),
               pre=[Remember("dest", FirstEmptyIn(["B"]))]),
        linear(PickFrom(MemRef("src")), PlaceAt(MemRef("dest")), Answer("answer_4")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — free the gripper first.",
        "answer_2": lambda e: f"There is nothing at {e.A}.",
        "answer_3": lambda e: f"{e.B} is full.",
        "answer_4": lambda e: f"Moved the object from {e.m('src')} to {e.m('dest')}.",
    },
))

task(TaskSpec(
    id="if_X_in_A_move_B", header="If there is an $X in $A, move it to $B", intent="move",
    variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("src"), Answer("answer_2")),
               pre=[Remember("src", FirstHoldingIn(["A"], X))]),
        branch(when(IsNone("dest"), Answer("answer_3")),
               pre=[Remember("dest", FirstEmptyIn(["B"]))]),
        linear(PickFrom(MemRef("src")), PlaceAt(MemRef("dest")), Answer("answer_4")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — free the gripper first.",
        "answer_2": lambda e: f"There is no {e.X} in {e.A} — nothing to move.",
        "answer_3": lambda e: f"{e.B} is full.",
        "answer_4": lambda e: f"Moved {e.X} from {e.m('src')} to {e.m('dest')}.",
    },
))

task(TaskSpec(
    id="find_X_move_if_at_A", header="Find an $X; if it is at $A, move it to $B, otherwise leave it",
    intent="move", variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A", "B"]))),
        branch(when(IsNone("src"), Answer("answer_2")),
               pre=[Remember("src", FirstHoldingIn(["A"], X))]),
        branch(when(IsNone("dest"), Answer("answer_3")),
               pre=[Remember("dest", FirstEmptyIn(["B"]))]),
        linear(PickFrom(MemRef("src")), PlaceAt(MemRef("dest")), Answer("answer_4")),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — free the gripper first.",
        "answer_2": lambda e: f"The {e.X} is not at {e.A} — leaving it.",
        "answer_3": lambda e: f"{e.B} is full.",
        "answer_4": lambda e: f"Moved {e.X} from {e.m('src')} to {e.m('dest')}.",
    },
))

task(TaskSpec(
    id="ensure_X_at_A", header="Ensure there is an $X at $A", intent="move",
    variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(ObserveEverything())),
        branch(when(has("A", X), Answer("answer_2"))),
        branch(when(IsNone("dest"), Answer("answer_3")),
               pre=[Remember("dest", FirstEmptyIn(["A"]))]),
        branch(when(IsNone("src"), Answer("answer_4")),
               pre=[Remember("src", FirstHolding(X, outside=["A"]))]),
        linear(PickFrom(MemRef("src")), PlaceAt(MemRef("dest")), Answer("answer_5")),
    ]),
    answers={
        "answer_1": lambda e: "Free the gripper first.",
        "answer_2": lambda e: f"{e.A} already has an {e.X}.",
        "answer_3": lambda e: f"{e.A} has no room for an {e.X}.",
        "answer_4": lambda e: f"There is no {e.X} anywhere else to bring.",
        "answer_5": lambda e: f"Brought an {e.X} from {e.m('src')} into {e.A} at {e.m('dest')}.",
    },
))

task(TaskSpec(
    id="drop_W_bring_X_back", header="You are holding $W. Drop it at $A, then bring an $X back to where you started",
    intent="move", held="W", variables=[OT("$W"), OT("$X", differ="$W"), LOC("$A")],
    program=Program([
        linear(CheckPosition(), Remember("start_position", Position()), ObserveEverything()),
        branch(when(IsNone("aloc"), Answer("answer_1")),
               pre=[Remember("aloc", FirstEmptyIn(["A"]))]),
        linear(PlaceAt(MemRef("aloc"))),
        branch(when(IsNotNone("xloc"),
                    PickFrom(MemRef("xloc")), GoTo(MemRef("start_position")), Answer("answer_2")),
               otherwise(GoTo(MemRef("start_position")), Answer("answer_3")),
               pre=[Remember("xloc", FirstHolding(X))]),
    ]),
    answers={
        "answer_1": lambda e: f"{e.A} is full — cannot drop {e.W}; did nothing.",
        "answer_2": lambda e: f"Dropped {e.W} at {e.A}, picked up an {e.X}, and returned to {e.m('start_position')}.",
        "answer_3": lambda e: f"Dropped {e.W} at {e.A}, but found no {e.X} anywhere; returned to {e.m('start_position')}.",
    },
))

task(TaskSpec(
    id="putdown_W_pick_X", header="You are holding $W. Put it down first, then pick up an $X",
    intent="pick", held="W", variables=[OT("$W"), OT("$X", differ="$W")],
    program=Program([
        linear(ObserveEverything()),
        branch(when(IsNone("wloc"), Answer("answer_1")),
               pre=[Remember("wloc", FirstEmpty())]),
        linear(PlaceAt(MemRef("wloc"))),
        branch(when(IsNotNone("xloc"), PickFrom(MemRef("xloc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Remember("xloc", FirstHolding(X))]),
    ]),
    answers={
        "answer_1": lambda e: f"There is nowhere to put {e.W} down — aborting.",
        "answer_2": lambda e: f"Put {e.W} down and picked up {e.X} from {e.m('xloc')}.",
        "answer_3": lambda e: f"Put {e.W} down, but there is no {e.X} anywhere.",
    },
))

task(TaskSpec(
    id="is_A_empty_else_report", header="Is $A empty? If so, go home; if not, tell me what is there",
    intent="move", variables=[LOC("$A")],
    program=Program([
        linear(Observe(["A"])),
        branch(when(is_empty("A"), GoTo("home"), Answer("answer_1")),
               otherwise(Answer("answer_2"))),
    ]),
    answers={
        "answer_1": lambda e: f"{e.A} is empty — went home.",
        "answer_2": lambda e: f"{e.A} contains: {e.desc('A')}.",
    },
))

task(TaskSpec(
    id="go_A_return", header="Go to $A, then come back to where you started", intent="move",
    variables=[LOC("$A")],
    program=Program([
        linear(CheckPosition(), Remember("start_position", Position())),
        linear(ApproachObserve("A"), GoTo(MemRef("start_position")), Answer("answer_1")),
    ]),
    answers={
        "answer_1": lambda e: f"Visited {e.A} and returned to {e.m('start_position')}.",
    },
))

task(TaskSpec(
    id="visit_A_then_B", header="Visit the observation points for $A and then $B", intent="move",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([
        linear(ApproachObserve("A"), ApproachObserve("B"), Answer("answer_1")),
    ]),
    answers={
        "answer_1": lambda e: f"I have visited observation points for {e.A} and {e.B}",
    },
))

task(TaskSpec(
    id="prepare_pick_X_empty_A", header="Prepare to pick $X from empty space in $A", intent="move",
    variables=[OT("$X"), LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        branch(when(IsNotNone("loc"), ApproachPick(X, TempRef("loc")), Answer("answer_2")),
               otherwise(Answer("answer_3")),
               pre=[Temp("loc", FirstEmptyIn(["A"]))]),
    ]),
    answers={
        "answer_1": lambda e: "Already holding something — have to drop it somewhere first.",
        "answer_2": lambda e: f"Prepared to pick {e.X} from {e.t('loc')}.",
        "answer_3": lambda e: f"There is no {e.X} in {e.A} and no empty location in {e.A}.",
    },
))


# ============================ navigation / status =======================

task(TaskSpec(
    id="go_home", header="Go to the home position", intent="move", variables=[],
    program=Program([linear(GoTo("home"), Answer("answer_1"))]),
    answers={"answer_1": lambda e: "I am at home"},
))

task(TaskSpec(
    id="go_observe_A", header="Go to the observation point for $A", intent="move",
    variables=[LOC("$A")],
    program=Program([linear(ApproachObserve("A"), Answer("answer_1"))]),
    answers={"answer_1": lambda e: f"I am at the observation point for {e.A}"},
))

task(TaskSpec(
    id="what_position", header="What position are you at?", intent="query", variables=[],
    program=Program([linear(CheckPosition(), Answer("answer_1"))]),
    answers={"answer_1": lambda e: f"I am at {e.position}"},
))

task(TaskSpec(
    id="am_i_home", header="Am I at home?", intent="query", variables=[],
    program=Program([linear(CheckPosition(), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        "Yes, I am at home." if e.position == "home" else f"No, I am at {e.position}.")},
))

task(TaskSpec(
    id="what_holding", header="What are you holding?", intent="query", variables=[],
    program=Program([linear(Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        "I don't hold anything" if e.state.gripper == "open"
        else "I hold something but I don't know what it is" if e.held == "unknown"
        else f"I am holding {e.held}")},
))

task(TaskSpec(
    id="am_i_holding_X", header="Am I holding $X?", intent="query", variables=[OT("$X")],
    program=Program([linear(Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        "No, I don't hold anything" if e.state.gripper == "open"
        else "I don't know, I hold something" if e.held == "unknown"
        else f"Yes, I am holding {e.X}" if e.held == e.binding.type_value("X")
        else f"No, I am holding {e.held}")},
))

task(TaskSpec(
    id="gripper_free", header="Is your gripper free?", intent="query", variables=[],
    program=Program([linear(Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        "Yes" if e.state.gripper == "open"
        else "No" if e.state.gripper == "closed" else "I don't know")},
))

task(TaskSpec(
    id="can_i_pick_A", header="Can I now pick something from $A?", intent="query",
    variables=[LOC("$A")],
    program=Program([
        linear(CheckGripper()),
        branch(when(gripper_is("closed"), Answer("answer_1")),
               otherwise(Observe(["A"]))),
        linear(Answer("answer_2")),
    ]),
    answers={
        "answer_1": lambda e: "No — I am already holding something.",
        "answer_2": lambda e: (
            f"Yes — the gripper is free and {e.A} has something to pick."
            if not e.is_empty("A")
            else f"No — the gripper is free but {e.A} is empty."),
    },
))


# ============================ observation queries =======================

task(TaskSpec(
    id="what_is_at_A", header="What is at $A?", intent="query", variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"{e.A} is empty" if e.is_empty("A") else f"There is {e.desc('A')}")},
))

task(TaskSpec(
    id="is_X_in_A", header="Is there $X in $A?", intent="query", variables=[OT("$X"), LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"No, there is no {e.X} in {e.A}" if not e.has("A", "X")
        else f"Yes, there is {e.X} in {e.join(e.locs_with('A', 'X'))}")},
))

task(TaskSpec(
    id="count_occupied_A", header="How many slots in $A are occupied?", intent="query",
    variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: f"{e.count('A')}"},
))

task(TaskSpec(
    id="any_empty_slots_A", header="Are there any empty slots in $A?", intent="query",
    variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"No, there are no empty slots in {e.A}" if e.is_full("A")
        else f"Yes, there are empty slots in {e.A}: {e.join(e.empty('A'))}")},
))

task(TaskSpec(
    id="which_slot_X_A", header="Which slot in $A has $X?", intent="query",
    variables=[OT("$X"), LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There is no {e.X} in {e.A}" if not e.has("A", "X")
        else e.join(e.locs_with("A", "X")))},
))

task(TaskSpec(
    id="which_has_X_A_or_B", header="Which has $X, $A or $B?", intent="query",
    variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There is no {e.X} in {e.A} or {e.B}"
        if not e.has("A", "X") and not e.has("B", "X")
        else f"There is {e.X} in {e.join(e.locs_with('A', 'X') + e.locs_with('B', 'X'))}")},
))

task(TaskSpec(
    id="count_by_type_A", header="Count objects by type in $A", intent="query",
    variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"{e.A} is empty" if e.is_empty("A")
        else "There are " + e.join(f"{n} {t}" for t, n in e.count_by_type("A").items())
        + f" in {e.A}.")},
))

task(TaskSpec(
    id="which_empty_in_A", header="Which locations in $A are empty right now?", intent="query",
    variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There are no empty locations in {e.A}." if e.is_full("A")
        else f"Empty locations in {e.A}: {e.join(e.empty('A'))}.")},
))

task(TaskSpec(
    id="is_A_empty", header="Is $A empty?", intent="query", variables=[LOC("$A")],
    program=Program([
        branch(when(is_empty("A"), Answer("answer_1")), otherwise(Answer("answer_2")),
               pre=[Observe(["A"])]),
    ]),
    answers={
        "answer_1": lambda e: f"Yes, {e.A} is empty.",
        "answer_2": lambda e: f"No, {e.A} is not empty.",
    },
))

task(TaskSpec(
    id="is_A_full", header="Is $A full?", intent="query", variables=[LOC("$A")],
    program=Program([
        branch(when(is_full("A"), Answer("answer_1")), otherwise(Answer("answer_2")),
               pre=[Observe(["A"])]),
    ]),
    answers={
        "answer_1": lambda e: f"Yes, {e.A} is full.",
        "answer_2": lambda e: f"No, {e.A} has empty space.",
    },
))

task(TaskSpec(
    id="how_many_X_in_A", header="How many $X are in $A?", intent="query",
    variables=[OT("$X"), LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: f"There are {e.count_type('A', 'X')} {e.X} in {e.A}."},
))

task(TaskSpec(
    id="how_many_empty_A", header="How many empty locations are there in $A?", intent="query",
    variables=[LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: f"There are {len(e.empty('A'))} empty locations in {e.A}."},
))

task(TaskSpec(
    id="anything_other_than_X_A", header="Is there anything other than $X in $A?", intent="query",
    variables=[OT("$X"), LOC("$A")],
    program=Program([linear(Observe(["A"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"Yes, {e.A} contains objects other than {e.X}."
        if e.count("A") > e.count_type("A", "X")
        else f"No, there is nothing other than {e.X} in {e.A}.")},
))

task(TaskSpec(
    id="more_in_A_or_B", header="Are there more objects in $A or $B?", intent="query",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"{e.A} has more objects." if e.count("A") > e.count("B")
        else f"{e.B} has more objects." if e.count("B") > e.count("A")
        else f"{e.A} and {e.B} have the same number of objects.")},
))

task(TaskSpec(
    id="same_count_A_B", header="Do $A and $B have the same number of objects?", intent="query",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"Yes, {e.A} and {e.B} have the same number of objects."
        if e.count("A") == e.count("B")
        else "No, they hold different numbers of objects.")},
))

task(TaskSpec(
    id="A_more_X_than_B", header="Does $A have more $X than $B?", intent="query",
    variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"Yes, {e.A} has more {e.X} than {e.B}."
        if e.count_type("A", "X") > e.count_type("B", "X")
        else f"No, {e.A} does not have more {e.X} than {e.B}.")},
))

task(TaskSpec(
    id="total_X_A_B", header="How many $X are there in total across $A and $B?", intent="query",
    variables=[OT("$X"), LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There are {e.count_type('A', 'X') + e.count_type('B', 'X')} {e.X} across {e.A} and {e.B}.")},
))

task(TaskSpec(
    id="list_all_X", header="List all the $X you can find", intent="query", variables=[OT("$X")],
    program=Program([linear(ObserveEverything(), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"I could not find any {e.X}." if not e.locations_holding("X")
        else f"{e.X} is at: {e.join(e.locations_holding('X'))}.")},
))

task(TaskSpec(
    id="both_A_B_empty", header="Are $A and $B both empty?", intent="query",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"Yes, both {e.A} and {e.B} are empty."
        if e.is_empty("A") and e.is_empty("B")
        else "No, at least one of them has something.")},
))

task(TaskSpec(
    id="either_A_B_empty", header="Is either $A or $B empty?", intent="query",
    variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"Yes, at least one of {e.A} or {e.B} is empty."
        if e.is_empty("A") or e.is_empty("B")
        else f"No, both {e.A} and {e.B} have something.")},
))

task(TaskSpec(
    id="total_objects_A_B", header="How many objects are there in total across $A and $B?",
    intent="query", variables=[LOC("$A"), LOC("$B", differ="$A")],
    program=Program([linear(Observe(["A", "B"]), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There are {e.count('A') + e.count('B')} objects across {e.A} and {e.B}.")},
))

task(TaskSpec(
    id="find_any_empty", header="Find any empty location and report it", intent="query",
    variables=[],
    program=Program([linear(ObserveEverything(), Answer("answer_1"))]),
    answers={"answer_1": lambda e: (
        f"There is an empty location at {e.first_empty_scene()}."
        if e.first_empty_scene() is not None
        else "There is no empty location anywhere.")},
))
