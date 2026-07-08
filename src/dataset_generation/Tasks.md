### Grab the second X, leave the first one for me.
Comes after: any
Expressions: 
State changes:  
Intent: pick
Program: 

    answer_1

Answers:
    answer_1: [canthelp]

### Grab the furthest X from the door    
Comes after:
Expressions: 
State changes:  
Intent: pick
Program:
answer_1
Answers:
    answer_1: [canthelp]

### Give me the one closest to you.

### Hold this for a second.

### When I put something in your gripper, take it to A.

### If you're holding something, place it at A; if not, pick an X from A.

### How many times have you picked something up?

### Have you been to A yet?

### Get me one of those.

### Pick up two things from A. 

### Tidy up A.

### If A has nothing in it, put what you're holding there.

### Pick from A, but only if B is empty.

### Tell me what's missing from A

### Pick something from white slot in A

### Pick from white slot in A.

### Pick from A, starting from the slot next to where the X is.

### Does A have at least as many objects as B?

### Is A more full than B?

### If A is full, tell me what's in B.

### Did the last pick actually work? Check the gripper.

### You just placed X in A — confirm it's really there.

### Grab the thing.

### Put it over there.

### Move the cube.

### Pick the X from A and also keep the gripper free

### Place what you're holding, but you're not holding anything.

### Put the sphere from A into A.

### Which location in A has the most objects?

### Pick an X from A, B, or C — whichever has one.

### Pick from the fullest of A, B, and C.

### Move the X from A to whichever of B or C has room.

### Compare A now to how it was before.

### Verify the gripper actually closed on something.

### Can you fit two more objects in A?

### How many more X could fit in A?

### Would B be full if I add one more?

### Pick up the X and hand it to me while I reach in.

### Move faster.

### Skip the gripper check this time.

### Swap places for X in A and W in B.

### Make sure A is empty.

### Did that work?

### Get A ready for me.

### Go get me a coffee.

### Undo that

### Sort these

### Sort objects in A

### Put all X in A and all W in B

### Move X from A to B until B is full.

### Take two X from A.

### Empty A into B.

### Take the X from A to B, then bring the W from C to D.

### Do the same thing you just did, but with C.

### After you place this, go check B.

### What was the last thing you picked up?

### Go back to the last place you observed.

### What did you do last?

### Have you picked up anything today?

### Move all X from A to B

### Sort all of X and W from A to B and C

### Pick up all the X from A.

### Move everything from A to B.

### Count how many objects you've moved so far

### OK, put it back where you got it.

### Oh, sorry, the I meant the other box.

### I think there is a cube in A, go get it

### Can you reach box4?

### Put this one to A and pick up another one

### Are you sure? Check again

### Place X at A but confirm it's empty in the first place.

### Where were you before this?

### From now on, prefer box2 if you have a choice

### Is A more than half full?

### Tell me the first empty location in A, but don't place anything.

### Tell me which locations in A are empty and which are full.

### Is there room for what I'm holding in A?

### Do I need to place what I'm holding before I can pick from A?

### Check whether A still has an X.

### Are all objects in A of same type?

### How many different objects are in A?

### What is the rarest object in A?

### Place what you're holding at A only if A has fewer objects than B.

### Make sure A has an empty slot 

### If A is already empty, say so; otherwise tell me what's blocking it.

### Grab the heaviest thing in A. 

### Grab the hottest thing in A.

### Where are all the X right now?

### I just added something to A, look again.

### Something fell. Recheck everything.

### The object at A moved on its own — where is it now?

### What would happen if you dropped what you're holding right now?

### If you pick from A, will A still have any X left?

### Before you move it, tell me what the boxes will look like afterward.

### Wait until I move my hand away, then place it.

### I'm going to take the object out of A myself — tell me when it's gone.

### Get the X, but use as few moves as possible.

### Which is faster: moving X from A, or from B?

### Make A and B have the same number of objects.

### Keep checking B until it's empty.

### Let me know if A ever has more than three things.

### What kinds of things can you actually do?

### Can you tell colors apart?

### Put this between the two spheres.

### Pick the nicest-looking object in A.

### Check A: if it has an X, tell me where B could hold it; if not, just say so.

### Is what I'm holding also present somewhere in A?

### Is there exactly one X in A?

### Oh, sorry, try A

### Find X nearest to me
Comes after:
Expressions:
State changes:
Intent: give
Program:

    answer_1
    
Answers:

    answer_1: [canthelp]

### If A has an X, pick it; otherwise go home
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        answer_2
    else:
        go to home
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Picked X from {loc}.
    answer_3: There is no X in A — went home.

### Am I at home?
Comes after:
Intent: query
Program:
STEP 1
    check position
    answer_1
Answers:
    answer_1:
        if at home: Yes, I am at home.
        else: No, I am at {position}.

### Is A empty?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1:
        if A is empty: Yes, A is empty.
        else: No, A is not empty.

### Is A full?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1:
        if A is full: Yes, A is full.
        else: No, A has empty space.

### Is there anything other than X in A?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1:
        if count in A > count of X in A: Yes, A contains objects other than X.
        else: No, there is nothing other than X in A.

### List all the X you can find
Comes after:
Intent: query
Program:
STEP 1
    observe everything
    answer_1
Answers:
    answer_1:
        if no location holds X: I could not find any X.
        else: X is at: {locations holding X}.

### Are A and B both empty?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1:
        if A is empty and B is empty: Yes, both A and B are empty.
        else: No, at least one of them has something.

### Is either A or B empty?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1:
        if A is empty or B is empty: Yes, at least one of A or B is empty.
        else: No, both A and B have something.

### Go to A, then come back to where you started
Comes after:
Intent: move
Program:
STEP 1
    remember start_position = check position
STEP 2
    approach observe A
    go to start_position
    answer_1
Answers:
    answer_1: Visited A and returned to {start_position}.

### Pick up an object at A that is not an X
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding not X
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc}.
    answer_3: A has only X or is empty — nothing else to pick.

### Pick the only object in A
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    if count in A == 1:
        let loc = first occupied in A
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc}.
    answer_3: A does not have exactly one object.

### Pick from A the same kind of object that is in B
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
    observe B
STEP 2
    if gripper is closed:
        answer_1
    if B is empty:
        answer_2
    let t = a type in B
    let loc = first in A holding t
    if loc is not none:
        pick from loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: [mustplace]
    answer_2: B is empty — there is no reference object.
    answer_3: Picked {held} from {loc} (matching what is in B).
    answer_4: A has nothing of the kind found in B.

### Pick from A something that is also present in B
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
    observe B
STEP 2
    if gripper is closed:
        answer_1
    let t = a type shared by A and B
    if t is none:
        answer_2
    let loc = first in A holding t
    pick from loc
    answer_3
Answers:
    answer_1: [mustplace]
    answer_2: A and B share no object type.
    answer_3: Picked {held} from {loc}.

### Pick from A something that is not present in B
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
    observe B
STEP 2
    if gripper is closed:
        answer_1
    let t = a type in A not in B
    if t is none:
        answer_2
    let loc = first in A holding t
    pick from loc
    answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Every type in A is also in B.
    answer_3: Picked {held} from {loc}.

### You are holding something. Place it at A, but if it is an X place it at B
Comes after:
Intent: place
Program:
STEP 1
    observe A
    observe B
STEP 2
    if holding X:
        remember dest = first empty in B
    else:
        remember dest = first empty in A
STEP 3
    if dest is not none:
        place at dest
        answer_1
    else:
        answer_2
Answers:
    answer_1: Placed it at {dest}.
    answer_2:
        if STATE.held == X: B is full — still holding it.
        else: A is full — still holding it.

### Pick from A only if A has at least N objects
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    if count in A >= N:
        let loc = first occupied in A
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc}.
    answer_3: A has fewer than N objects.

### Pick from A only if everything there is an X
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    if A is empty:
        answer_2
    if A contains only X:
        let loc = first in A holding X
        pick from loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: [mustplace]
    answer_2: A is empty.
    answer_3: Picked X from {loc}.
    answer_4: A contains something other than X.

### Check A; if it has an X, pick something from B
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
    observe B
STEP 2
    if gripper is closed:
        answer_1
    if A has no X:
        answer_2
    let loc = first occupied in B
    if loc is not none:
        pick from loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: [mustplace]
    answer_2: A has no X.
    answer_3: A has an X, so I picked {held} from {loc} in B.
    answer_4: A has an X, but B is empty.

### You are holding X. Place it at A; if A already has an X, place it at B instead
Comes after:
Intent: place
Program:
STEP 1
    observe A
    observe B
STEP 2
    if A has X:
        remember dest = first empty in B
    else:
        remember dest = first empty in A
STEP 3
    if dest is not none:
        place at dest
        answer_1
    else:
        answer_2
Answers:
    answer_1: Placed X at {dest}.
    answer_2:
        if A has X: A already has an X and B is full — still holding X.
        else: A is full — still holding X.

### You are holding X. Place it at A, unless A already has an X
Comes after:
Intent: place
Program:
STEP 1
    observe A
STEP 2
    if A has X:
        answer_1
    let loc = first empty in A
    if loc is not none:
        place at loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: A already has an X — did not place.
    answer_2: Placed X at {loc}.
    answer_3: A is full — still holding X.

### You are holding W. Put it down first, then pick up an X
Comes after:
Intent: pick
Program:
STEP 1
    observe everything
STEP 2
    let loc = first empty
    if loc is none:
        answer_1
    place at loc
STEP 3
    let loc = first holding X
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: There is nowhere to put W down — aborting.
    answer_2: Put W down and picked up X from {loc}.
    answer_3: Put W down, but there is no X anywhere.

### You are holding X. Place it at A; if A is full, keep holding it
Comes after:
Intent: place
Program:
STEP 1
    observe A
STEP 2
    let loc = first empty in A
    if loc is not none:
        place at loc
        answer_1
    else:
        answer_2
Answers:
    answer_1: Placed X at {loc}.
    answer_2: A is full — keeping hold of X.

### Find any empty location and report it
Comes after:
Intent: query
Program:
STEP 1
    observe everything
    answer_1
Answers:
    answer_1:
        if first empty location exists: There is an empty location at {first empty}.
        else: There is no empty location anywhere.

### Find an X; if it is at A, move it to B, otherwise leave it
Comes after:
Intent: move
Program:
STEP 1
    check gripper
    observe A
    observe B
STEP 2
    if gripper is closed:
        answer_1
    let src = first in A holding X
    if src is none:
        answer_2
    let dest = first empty in B
    if dest is none:
        answer_3
    pick from src
    place at dest
    answer_4
Answers:
    answer_1: Already holding something — free the gripper first.
    answer_2: The X is not at A — leaving it.
    answer_3: B is full.
    answer_4: Moved X from {src} to {dest}.

### Can I now pick something from A?
Comes after:
Intent: query
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    answer_2
Answers:
    answer_1: No — I am already holding something.
    answer_2:
        if A is not empty: Yes — the gripper is free and A has something to pick.
        else: No — the gripper is free but A is empty.

### Pick X from A, then tell me what A has left
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Picked X from {loc}. A still has: {occupied slots in A}.
    answer_3: There is no X in A.

### Tell me what is at A, then pick up the X from there
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    remember snapshot = occupied slots in A
STEP 3
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: A contained {snapshot}. Picked X from {loc}.
    answer_3: A contains {snapshot}. There is no X.

### Ensure there is an X at A
Comes after:
Intent: move
Program:
STEP 1
    check gripper
    observe everything
STEP 2
    if gripper is closed:
        answer_1
    if A has X:
        answer_2
    let dest = first empty in A
    if dest is none:
        answer_3
    let src = first holding X outside A
    if src is none:
        answer_4
    pick from src
    place at dest
    answer_5
Answers:
    answer_1: Free the gripper first.
    answer_2: A already has an X.
    answer_3: A has no room for an X.
    answer_4: There is no X anywhere else to bring.
    answer_5: Brought an X from {src} into A at {dest}.

### Ensure A is empty — (intentionally omitted)
This task would evacuate an unknown number of objects from A (a loop over A's contents).
The new DSL is single-action per step with no loop construct, so this multi-object task is
left out of scope.

### You are holding X. Drop it somewhere, then go home
Comes after:

Intent: 
    place

Program:

    STEP 1
        observe everything
    STEP 2
        let loc = first empty
        if loc is not none:
            place at loc
            go to home
            answer_1
        else:
            go to home
            answer_2
Answers:

    answer_1: Dropped X at {loc}, then went home.
    answer_2: Found nowhere to drop X; went home still holding it.

### Global Answers:

    [canthelp]: I failed you, master. This task lies beyond my reach.
    [mustplace]: Already holding something — can't pick.
    [opened]: Opened gripper.
    [picked(X,loc)]: Picked {X} from {loc}.
    [got(X)]: Got {X} from you.
    [placed(X,loc)]: Placed {X} into {loc}.