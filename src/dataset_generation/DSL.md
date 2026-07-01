# Pick-and-Place DSL

A DSL the LLM emits to drive a pick-and-place robot. The LLM is the only stateful component. Every value the next invocation needs appears in the current invocation's output; the system keeps the most recent of each block in context plus turn history.

---

## 0. Assumptions

- Scene changes during turn execution have no effect on execution. Every change in scene between turns is told to the model explicitly.
- Tasks given by user may have wrong assumptions about the scene state, but are unequivocal for any scene configuration.

---

## 1. Execution model

### 1.1 Vocabulary

- **Conversation**: Collection of turns. Is interrupted by user (starting new conversation). `scans`, `position`, `gripper`, `held` carry across turns.
- **Turn**: one user prompt and the model's response. May span many invocations.
- **Invocation**: one LLM forward pass.
- **Step**: one numbered unit in PROGRAM. One step = one invocation.
- **This turn**: after the last user message
- **Location** is a single slot in the scene, can only contain one object at most
- **Location Collection** is name of a group of one or more Locations
- **Target** is a **Location** or multiple **Location** or **Location Collection** or multiple **Location Collection**
- **Context manager** is a program that parses and keeps track of the blocks and user messages and passes the right input to the model based on conditions described

### 1.2 Roles and Blocks.

There are messages of only two roles: `ASSISTANT` and `USER`. Note, I don't use typical tool message role, instead write tool results as special blocks into assistant messages.

For `ASSISTANT` messages, there are following blocks: `PROGRAM` `MEMORY` `RESOLUTION` `TOOL CALL` `TOOL RESULT` `ANSWER`.

 
```
PROGRAM
L1 <primitive>
L2 <primitive>
...
```

```
MEMORY
<Name1>: <Value1>
<Name2>: <Value2>
...
```
```
RESOLUTION
L1 <resolution line>
   <resolution line>
L2 <resolution line>
...
```
```
TOOL CALL
tool name 1 (argument name = argument value, ...) <-- in this case tool call result will be rendered in TOOL CALL block
OR
key = tool name 2 (argument name = argument value, ...) <-- in this case toool call result will be saved unter key in MEMORY by context manager
```
```
TOOL RESULT
tool name (argument name = argument value) = tool output
```

Here are update rules and existence periods of blocks

| Block | Update rules | Exists until next |
|--------|--------| --------|
| `PROGRAM` | Each reemition of this block completely rewrites it. | Turn |
| `MEMORY` | Context Manager parses names and rewrites values or appends new name-value pair. | Conversation |
| `RESOLUTION` | Each reemition of this block completely rewrites it. | Turn |
| `TOOL CALL` | On each emition, new block content is appended to existing. | RESOLUTION update |
| `TOOL RESULT` | Each reemition of this block completely rewrites it. | Invocation | 

### 1.3 Execution

Input is always the same: all existing user message - answer pairs + all the blocks in the most recent state (if some block doesn't exist yet, it doesn't get appended)

Model outputs program and then executes it line by line until ANSWER block is emitted, in this case the context manager shows answer to user. If the program is done (cursor = done) but no ANSWER is emitted, execution continues, model is expected to output new program.

How the program is executed you can see in the walkthroughs.

### 1.4 Special memory keys

There are a couple of special memory keys that are "reserved" for things model might need in most cases. They are not "hard" reserved, it's just a convention on how the model is trained. Further we call them state.

| key | stores |
|------|--------|
| current position | current robot position from positions list / unknown |
| gripper | gripper closed / open / unknown |
| held | currently held object / unknown |
| explored observation positions | list[observation position1, observation position2, ...] |
| cursor | next line of program to execute Li / done |
| scans | dict{location1: object1 / empty, location2: object2 / empty, ...} |
| positions | list of positions present in scene |
| objects | list of objects present in scene |
| locations | list of locations present in scene |

### 1.5 Tool effects on state

| Tool | Effect |
|------|--------|
| `move_to(position=P)` | `position := P` |
| `locate_shapes()` | append current `position` to `explored observation positions`; merge returned `slot → object / empty` into `scans` |
| `open_gripper()` | `gripper := open`; `held := none` |
| `close_gripper()` | `gripper := closed`; 1. if executed via pick primitive: `held := T` if currently in `pick_<T>_<L>` position, also location: empty in object dictionary 2. if executed via get X from user primitive: `held := X`, 3. otherwise: `held := unknown` |
| `get_gripper_state()` | `gripper := <return>`; if `open`, `held := none` |
| `get_position_state()` | `position := <return>` |

After a successful `pick X from L`: `scans[L]` is removed.
After a successful `place X at L`: `scans[L] := X`.

The model applies these effects when rewriting STATE for the next invocation.

User-stated state changes ("you are holding a cube") are applied directly: the model writes the corresponding STATE update in the same invocation it emits the program.

---

## 2. PROGRAM and RESOLUTION

### 2.1 What a program is
 
A PROGRAM is an ordered sequence of lines emitted as the `PROGRAM` block, RESOLUTION is like a notebook used to help the model execute the program. The way it works is that model writes program line resolutions one after another, if some program line is trivial model still writes number of that line in resolution. Multiple resoloution lines to one program line are allowed.

### 2.2 Position-name pattern notation
 
`pick_<T>_<L>`, `place_<T>_<L>`, and observe poses like `observe_<L>` denote entries in the position list whose structure encodes the action. The actual entry string is whatever the position list contains; the LLM finds the matching entry by structural match on `<T>` and `<L>`

### 2.3 Data types

Model must be trained to use following data types, besides strings and numbers.

| Data type | Description |
|-----------|-----------|
| `list` | python-like list |
| `counter` | python-like list with counts [elem1: count1, elemt2: count2,...] count is an int |
| `dict` | python-like dictionary |
| `string` | python-like string |

Here is how state variables match these data types:

| state variable | data type |
|-----------|-----------|
| `scans` | `dict` |
| `objects`, `locations` | `list` |
| `dictionary` | python-like dictionary |
| `dictionary` | python-like dictionary |

### 2.4 Expressions on data types

Counter

| Expression | Value |
|-----------|-----------------|
| count of `X` in `counter` | count of X in counter |
| N-biggest count in `counter` | N-biggest count in counter |
| N-smallest count in `counter` | N-smallest count in counter |
| N-biggest in `counter` | X in counter that has N-biggest count |
| N-smallest in `counter` | X in counter that has N-smallest count |

List

| Expression | Value |
|-----------|-----------------|
| first in `list` | list[0] |
| parse `list` for objects | saves `objects` list of objects whose existence follows from the list|
| parse `list` for locations | saves `locations` list of locations whose existence follows from the list|

Dict

| Expression | Value |
|-----------|-----------------|
| keys in `dict` where value is `[list of values]` | `list` of keys with value matching any value in the list |
| keys in `dict` where value is not `[list of values]` | `list` of keys with value not matching any value in the list |
| `dict[keys group]` | `dict` that is obtained from original one by deleting all keys not matching `keys group` semantically (LLM decides) |

String

| Expression | Value |
|-----------|-----------------|
| `string` is `value` | bool comparison |

### 5.5 Primitives
 
Further:

`<X>, <W>` are always object types: either left hand sides in **MEMORY** or names derived from positions list.

`<A>, <B>` is always target: either left hand sides in **MEMORY** or names derived from positions list.

`<L> or <location>` is always single location: either left hand sides in **MEMORY** or name derived from positions list.

`<Position> or <P>` must always be a valid left hand side in the **MEMORY** that equals a valid position from the position list or a position from position list

#### 5.5.1 Simple actions
 
| Primitive | Tool calls | Resolution lines | Precondition |
|-----------|-----------|------------------|--------------|
| `go to <Position>` | `move_to(position=<Position>)` | (none) | — |
| `open gripper` | `open_gripper()` | (none) | — |
| `close gripper` | `close_gripper()` | (none) | — |
| `check gripper` | `get_gripper_state()` | (none) | — |
| `check position` | `get_position_state()` | (none) | — |
| `locate here` | `locate_shapes()` | (none) | — |

#### 5.5.2 Observe actions
| Primitive | Tool calls | Resolution lines | 
|-----------|-----------|------------------|
| `approach observation <A>` (drop `[]` if single argument) | For some observe pose `P` covering some location in `<A>`: `move_to(P)`. | `observe poses = [P1, P2, ...]` |
| `observe <A1>, <A2>, ...` | Let `P1, P2, ...` be the smallest list of positions covering all locations in `<A1>, <A2>, ...` and `P ∉ explored observation positions`: `move_to(P); locate_shapes()`. | `observe poses = [P1, P2, ...]` |
| `observe everything` | Let `P1, P2, ...` be the smallest list of positions covering all locations and `P ∉ explored observation positions`: `move_to(P); locate_shapes()`. | `observe poses = [P1, P2, ...]` |

#### 5.5.3 Pick and place actions
| Primitive | Tool calls | Resolution lines | Precondition |
|-----------|-----------|------------------|--------------|
| `approach pick of <X> at <A>` | `move_to(position=pick_<X>_<L>)` | (none beyond `<X>` / `<A>` helpers, if any) | none |
| `pick from <A>` | `move_to(pick_<X>_<L>); close_gripper()` | `L = <A> = <location>`<br>`T = scans[<L>] = <type>` | gripper open; `<A>` resolves to a single Location `L`; `L ∈ MEMORY.scans` |
| `get <X> from user` | `close_gripper()` | getting <X> | |
| `give <held> to user` | `open_gripper()` | giving <held>> | |
| `approach place of <X> at <A>` | `move_to(place_<X>_<L>)` | (none beyond `<X>` / `<A>` helpers, if any) | `<L>` is known empty |
| `place at <A>` | `move_to(place_<X>_<L>); open_gripper()` | `L = <A> = <location>`<br>`X = held = <type>` | gripper closed; `MEMORY.held` is an ObjectType (not `none`, not `unknown`); `<A>` resolves to a single Location `L`; `L` is known empty |

#### 5.5.4 Memory

| Primitive | Effect | Resolution lines |
|-----------|--------|------------------|
| `remember <name> = <Expr>` | After the step's tool calls run, resolve `<Expr>` against the post-tools STATE and write the value to `MEMORY[<name>]`. | `<Expr> = <value>`|

`<name>` from `remember <name> = <Expr>` can also be used by the model as temporary variable!

#### 5.5.6 Temporary variables

As opposed to memory, these are not written to memory block and not preserved across steps. Model only writes them in the resolution block.
 
| Primitive | Effect | Resolution lines |
|-----------|--------|------------------|
| `let <name> = <expression>` | Model should emit `<name> = <expression value>` in the resolution block and use the variable further in the step | `<name> = <expression value>` |

---

## 10. Walkthroughs

### 10.1 Simple pick

**User task:** "Pick up a cube from box1"

**Position list:** "pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"

---

#### Invocation 1

Input
```
User: pick up a brick from the first box
```
Output
```
PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = L1
position = unknown
gripper = unknown
held = unknown
```

---

#### Invocation 2

Input
```
User: pick up a brick from the first box

PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = L1
position = unknown
gripper = unknown
held = unknown
```
Output
```
RESOLUTION
L1

MEMORY
cursor = L2

TOOL CALL
positions = get_positions()
```

---

#### Invocation 3

Input
```
User: pick up a brick from the first box

PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = L2
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
```
Output
```
RESOLUTION
L2 

MEMORY
cursor = L3
objects = ["cube"]
```

---

#### Invocation 4

Input
```
User: pick up a brick from the first box

PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = L3
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
```
Output
```
RESOLUTION
L3

MEMORY
cursor = L4
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
```

#### Invocation 5

Input
```
User: pick up a brick from the first box

PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = L4
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
```
Output
```
RESOLUTION
L4 

MEMORY
cursor = done
brick = cube
first box = ["box1_1", "box1_2"]
```

---

#### Invocation 6

Input
```
User: pick up a brick from the first box

PROGRAM
L1 remember positions = get positions
L2 parse positions for objects
L3 parse positions for locations
L4 parse user

MEMORY
cursor = done
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]
```
Output
```
PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L1
```

---

#### Invocation 7

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L1
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]
```
Output
```
RESOLUTION
L1 

MEMORY
cursor = L2

TOOL CALL
check_gripper()
```

---

#### Invocation 8

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L2
position = unknown
gripper = unknown
held = unknown
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

TOOL RESULTS
check_gripper = {status:"OK", content: "open"}

```
Output
```
MEMORY
gripper = open
held = none

```
---
#### Invocation 9

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L2
position = unknown
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

```
Output
```
RESOLUTION
L2 gripper is closed = False
   selected: L5
L5 observe positions = ["observe_box1"]

MEMORY
cursor = L6

TOOL CALL
move_robot_to(position="observe_box1")
```
---
#### Invocation 10

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L6
position = unknown
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

RESOLUTION
L2 gripper is closed = False
   selected: L5
L5 observe positions = "observe_box1"

TOOL CALL
move_robot_to(position="observe_box1")

TOOL RESULTS
move_robot_to(position="observe_box1") = {status: OK, content: ""}

```
Output
```
MEMORY
position = "observe_box1"

TOOL CALL
locate_shapes()

```
---
#### Invocation 11

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L6
position = "observe_box1"
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

RESOLUTION
L2 gripper is closed = False
   selected: L5
L5 observe positions = "observe_box1"

TOOL CALL
move_robot_to(position="observe_box1")
locate_shapes()

TOOL RESULTS
locate_shapes = {status: OK, content: {box1_1: cube}}

```
Output
```
MEMORY
explored observation positions = "observe_box1"
objects = {"box1_1": "cube", "box1_2": "empty"}
```

---

#### Invocation 12

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L6
position = "observe_box1"
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
explored observation positions = "observe_box1"
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

RESOLUTION
L2 gripper is closed = False
   selected: L5
L5 observe positions = "observe_box1"


TOOL CALL
move_robot_to(position="observe_box1")
locate_shapes()
```
Output
```
RESOLUTION
L6 MEMORY.scans[first box] = {box1_1: cube, box1_2: empty}
   MEMORY.scans[first box] where value is cube = ["box1_1"]
   temp loc = "box1_1"
L7 loc is not none = True
   selected: L8
L8 pick location = "box1_1"
   pick object = cube

MEMORY
cursor = L9

TOOL CALL
move_robot_to(position="pick_cube_box1_1")
```
---

#### Invocation 13

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L9
position = "observe_box1"
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
explored observation positions = "observe_box1"
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

RESOLUTION
L6 temp loc = box1_1
L7 loc is not none = True
   selected: L8
L8 pick location = box1_1
   pick object = cube

TOOL CALL
move_robot_to(position="pick_cube_box1_1")

TOOL RESULTS
move_robot_to(position="pick_cube_box1_1") = {status: OK, content: ""}
```
Output
```
MEMORY
position = "pick_cube_box1_1"

TOOL CALL
close_gripper()
```
---

#### Invocation 14

Input
```
User: pick up a brick from the first box

PROGRAM
L1 check gripper
L2 if gripper is closed:
L3   answer_1
L4 else:
L5   observe first box
L6 temp loc = first in MEMORY.scans[first box] where value is cube
L7 if loc is not none:
L8   pick from loc
L9   answer_2
L10 else:
L11  answer_3

MEMORY
cursor = L9
position = "observe_box1"
gripper = open
held = none
positions = {status: OK, content:["pick_cube_box1_1", "pick_cube_box1_2", "place_cube_box1_1", "place_cube_box1_2" "observe_box1", 
"pick_cube_box2_1", "pick_cube_box2_2", "place_cube_box2_1", "place_cube_box2_2", "observe_box2"]}
explored observation positions = "observe_box1"
objects = ["cube"]
locations = ["box1_1", "box1_2", "box2_1", "box2_2"]
brick = cube
first box = ["box1_1", "box1_2"]

RESOLUTION
L6 temp loc = box1_1
L7 loc is not none = True
   selected: L8
L8 pick location = box1_1
   pick object = cube

TOOL CALL
move_robot_to(position="pick_cube_box1_1")
close_gripper()

TOOL RESULTS
close_gripper() = {status: OK, content: ""}
```
Output
```
RESOLUTION
L9 

MEMORY
cursor = done

ANSWER
Picked up cube from pick_cube_box1_1
```
---

End of spec.