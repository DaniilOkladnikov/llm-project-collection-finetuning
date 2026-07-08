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
- **This turn**: after the last user message
- **Location** is a single slot in the scene, can only contain one object at most
- **Location Collection** is name of a group of one or more Locations
- **Target** is a **Location** or multiple **Location** or **Location Collection** or multiple **Location Collection**
- **Context manager** is a program that parses and keeps track of the blocks and user messages and passes the right input to the model based on conditions described

### 1.2 Roles and Blocks.

There are messages of only two roles: `ASSISTANT` and `USER`. Note, I don't use typical tool message role, instead write tool results as special blocks into assistant messages.

For `ASSISTANT` messages, there are following blocks: `PROGRAM` `MEMORY` `RESOLUTION` `TOOL CALL` `TOOL RESULTS` `ANSWER`.

 
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
TOOL RESULTS
tool name (argument name = argument value) = tool output
```

Here are update rules and existence periods of blocks

| Block | Update rules | Exists until next |
|--------|--------| --------|
| `PROGRAM` | Each reemition of this block completely rewrites it. | Turn |
| `MEMORY` | Context Manager parses names and rewrites values or appends new name-value pair. | Conversation |
| `RESOLUTION` | Each reemition of this block completely rewrites it. | Turn |
| `TOOL CALL` | On each emition, new block content is appended to existing. | RESOLUTION update |
| `TOOL RESULTS` | Each reemition of this block completely rewrites it. | Invocation | 
| `ANSWER` | Each reemition of this block completely rewrites it. | Invocation | 

### 1.3 Execution

Input is always the same: all existing user message - answer pairs + all the blocks in the most recent state (if some block doesn't exist yet, it doesn't get appended)

Model outputs program and then executes it line by line until ANSWER block is emitted, in this case the context manager shows answer to user. If the program is done (cursor = done) but no ANSWER is emitted, execution continues, model is expected to output new program.

How the program is executed you can see in the walkthroughs.

On tool call batching, the RESOLUTION ends at the first primitive requiring tool call or a memory write. It just so happens primtives may require multiple. In this case multiple are made one-by-one.

About position names: the runner must resolve positions by structural match on the scene's positions fields (type, bound_type, bound_location, observable_locations), never by formatting a string.

MEMORY is output by the model as delta, but context manager adds new keys and rewrites old ones and then prints the whole memory in the next input

scans is populated fot the whole revealed set, even if it's bigger than original A that triggerd observation.

### 1.4 Special memory keys

There are a couple of special memory keys that are "reserved" for things model might need in most cases. They are not "hard" reserved, it's just a convention on how the model is trained. Further we call them state.

| key | stores |
|------|--------|
| current position | current robot position from avaliable positions list / unknown |
| gripper | gripper closed / open / unknown |
| held | currently held object / unknown |
| explored observation positions | list[observation position1, observation position2, ...] |
| cursor | points at first line of RESOLUTION to execute, update leads to new RESOLUTION / done, in this case leads to new program if answer wasn't emitted |
| scans | dict{location1: object1 / empty, location2: object2 / empty, ...} |
| avaliable positions | list of positions present in scene |
| objects | list of objects present in scene |
| locations | list of locations present in scene |

About positions: In practice avaliable positions wil be whatever the tool returns, usually a dict with status, but it will contain content with positions list, avaliable positions will be treated as the content in this case.

About cursor: the model pushes cursor to the next state when the previous resolution has been completed. This may take multiple invocations (because multiple tool calls). Cursor isn't advanced until the current resolution isn't completed. Model judges it's comletion by comparing made tool calls and memory state with resolution lines.

About two tool-call forms. 1) remember key = tool(): context manager saves the result to MEMORY. 2) plain tool() form: result goes to TOOL RESULTS

### 1.5 Tool effects on state

| Tool | Effect |
|------|--------|
| `move_robot_to(position=P)` | `position := P` |
| `locate_shapes()` | append current `position` to `explored observation positions`; merge returned `slot → object / empty` into `scans`. Note that tool only returns nonempty slots, model derives slots that would be in return if they were non-empty and labels them as empty |
| `open_gripper()` | `gripper := open`; `held := none` |
| `close_gripper()` | `gripper := closed`; 1. if executed via pick primitive: `held := T` if currently in `pick_<T>_<L>` position, also location: empty in object dictionary 2. if executed via get X from user primitive: `held := X`, 3. otherwise: `held := unknown` |
| `get_gripper_state()` | `gripper := <return>`; if `open`, `held := none` |
| `get_position_state()` | `position := <return>` |

The model applies these effects when rewriting state variables in memoty for the next invocation.

User-stated state changes ("you are holding a cube") are applied directly: the model writes the corresponding state variables in memory update in the same invocation it emits the program.

---

## 2. PROGRAM and RESOLUTION

### 2.1 What a program is
 
A PROGRAM is an ordered sequence of lines emitted as the `PROGRAM` block, RESOLUTION is like a notebook used to help the model execute the program. The way it works is that model writes program line resolutions one after another, if some program line is trivial model still writes number of that line in resolution. Multiple resoloution lines to one program line are allowed.

Conditionals are allowed in the program

if, elif, else. Line with conditional is resolved like this:

For example let:
L1 if cond
L2 something
L3 elif cond2
L4 something2
L5 else
L6 something3
Then:

RESOLUTION
...
L1 cond = True
   selected: L2
L2 ...

OR 

RESOLUTION
...
L1 cond = False
   selected: L3
L3 cond2 = True
   selected: L4
L4 ...

OR

RESOLUTION
...
L1 cond = False
   selected: L3
L3 cond2 = False
   selected: L5
L5
L6 ...

### 2.2 Position-name pattern notation
 
`pick_<T>_<L>`, `place_<T>_<L>`, and observe poses like `observe_<L>` denote entries in the position list whose structure encodes the action. The actual entry string is whatever the position list contains; the LLM finds the matching entry by structural match on `<T>` and `<L>`

### 2.3 Data types

Model must be trained to use following data types, besides strings and numbers.

| Data type | Description |
|-----------|-----------|
| `list` | python-like list |
| `dict` | python-like dictionary |
| `string` | python-like string |

Here is how state variables match these data types:

| state variable | data type |
|-----------|-----------|
| `scans` | `dict` |
| `avaliable positions` `objects`, `locations` | `list` |

### 2.4 Expressions on data types

List

| Expression | Value |
|-----------|-----------------|
| first in `list` | list[0] |
| parse `list` for objects | saves `objects` list of objects whose existence follows from the list|
| parse `list` for locations | saves `locations` list of locations whose existence follows from the list|

Dict

| Expression | Value |
|-----------|-----------------|
| `dict` where value is `[list of values]` | `list` of keys with value matching any value in the list |
| `dict` where value is not `[list of values]` | `list` of keys with value not matching any value in the list |
| `dict[keys group]` | `dict` that is obtained from original one by deleting all keys not matching `keys group` semantically (LLM decides) |

String

| Expression | Value |
|-----------|-----------------|
| `string` is `value` | bool comparison |

Expressions are resolved in format expression = value. If expressions are nested, resolution goes inside-out line by line one expression at the time until the outermost is resolved

### 5.5 Primitives
 
Further:

`<X>, <W>` are always object types: either left hand sides in **MEMORY** or names derived from avaliable positions list.

`<A>, <B>` is always target: either left hand sides in **MEMORY** or names derived from positions list.

`<L> or <location>` is always single location: either left hand sides in **MEMORY** or name derived from avaliable positions list.

`<Position> or <P>` must always be a valid left hand side in the **MEMORY** that equals a valid position from the position list or a position from position list

#### 5.5.1 Simple actions
 
| Primitive | Tool calls | Resolution lines | Precondition |
|-----------|-----------|------------------|--------------|
| `open gripper` | `open_gripper()` | (none) | — |
| `close gripper` | `close_gripper()` | (none) | — |
| `check gripper` | `get_gripper_state()` | (none) | — |
| `check position` | `get_position_state()` | (none) | — |
| `locate here` | `locate_shapes()` | (none) | — |

#### Parse user

parse user primitive saves to memory how user named entities of the scene: positions, locations and objects. No resolution. Emits N memory keys, one per parsable entity in the prompt.

#### Moving actions

| `go to <P>` | `move_robot_to(position=<Position>)` | position = (position(P)) <- converts position-alike P to a real position name | — |
| `go to pick X from loc` | `move_robot_to(position=<Position>)` for mentioned pick position| position = pick_X_loc <- real position name| — |
| `go to place X from loc` | `move_robot_to(position=<Position>)` for mentioned place position| position = place_X_loc <- real position name | — |
| `go to observation of A` | `move_robot_to(position=<Position>)` for mentioned observation position| position = observe_<L> <- real position name | — |

#### 5.5.2 Observe actions
| Primitive | Tool calls | Resolution lines | 
|-----------|-----------|------------------|
| `observe <A1>, <A2>, ...` | Let `P1, P2, ...` be the smallest list of positions covering all locations in `<A1>, <A2>, ...` and `P ∉ explored observation positions`: `move_robot_to(P); locate_shapes()`. | `observation positions = [P1, P2, ...]` |
| `observe everything` | Let `P1, P2, ...` be the smallest list of positions covering all locations and `P ∉ explored observation positions`: `move_robot_to(P); locate_shapes()`. | `obseration positions = [P1, P2, ...]` |

#### 5.5.3 Pick and place actions
| Primitive | Tool calls | Resolution lines | Precondition |
|-----------|-----------|------------------|--------------|
| `pick from <loc>` | `move_robot_to(pick_<X>_<loc>); close_gripper()` | pick location = <loc> <br>pick object = scans[ <loc> ] | gripper open; `<A>` resolves to a single Location `L`; `L ∈ MEMORY.scans` |
| `get <X> from user` | `close_gripper()` | getting <X> | |
| `give <held> to user` | `open_gripper()` | giving <held>> | |
| `place in <loc>` | `move_robot_to(place_<X>_<L>); open_gripper()` | `L = <loc> = <location>`<br>`X = held = <type>` | gripper closed; `MEMORY.held` is an ObjectType (not `none`, not `unknown`); `<A>` resolves to a single Location `L`; `L` is known empty |

#### 5.5.4 Memory

| Primitive | Effect | Resolution lines |
|-----------|--------|------------------|
| `remember <name> = <Expr>` | After the step's tool calls run, resolve `<Expr>` against the post-tools STATE and write the value to `MEMORY[<name>]`. | `<Expr> = <value>`|

End of spec.