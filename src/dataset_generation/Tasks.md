### Pick up X from A
Comes after:
Expressions: first location in A holding X, gripper is closed, is not none
State changes:  
Intent: pick
Program:
STEP 1
check gripper
STEP 2
    if gripper is closed:
        answer_1
    else:
        observe A
STEP 3
    let loc = first location in A holding X
    if loc is not none:
        pick from loc
        answer_2
    else: 
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: [picked(X,loc)].
    answer_3: There is no X in A.

### Close gripper, I am giving you X
Comes after:
Expressions: gripper is closed
State changes: 
Intent: get
Program: 
STEP 1
check gripper
STEP 2
    if gripper is closed:
        answer_1
    else:
        get X from user 
        answer_2
Answers:
    answer_1: [mustplace]
    answer_2: Got X from you.

### Come to A and get X from me
Comes after:
Expressions: 
State changes:
Intent: get
Program:
Step 1
answer_1
Answers:
answer_1: Please separate your commands for safety. Tell me where to move first, and hand me the item in the next step.

### You are holding X. Place it into A
Comes after:
Expressions: is not none, first empty 
State changes: gripper: closed, held: X
Intent: place
Program:
STEP 1
    observe A
STEP 2
    let loc = first empty location
    if loc is not none:
        place at loc
        answer_1
    else:
        answer_2 
Answers: 
    answer_1: Placed X in A.
    answer_2: There is no empty space in A.

### What are you holding?
Comes after: 
Expressions: 
State changes: 
Intent: query
Program:
STEP 1
    answer_1
Answers:
    answer_1: 
        if STATE.gripper == open: I don't hold anything
        elif STATE.held == unkown: I hold something but I don't know what it is
        else: I am holding STATE.held

### Am I holding X?
Comes after: 
Expressions: 
State changes: 
Intent: query
Program:
STEP 1
    answer_1
Answers:
    answer_1: 
        if STATE.gripper == open: No, I don't hold anything
        elif STATE.held == unkown: I don't know, I hold something
        elif STATE.held == X: Yes, I am holding X
        else: No, I am holding STATE.held

### Is your gripper free?
Comes after:
Expressions: 
State changes:  
Intent: query
Program:
STEP 1
    answer_1
Answers:
    answer_1: 
        if STATE.gripper == open: Yes
        elif STATE.gripper == closed: No
        else: I don't know

### What position are you at?
Comes after: 
Expressions: 
State changes: 
Intent: query
Program: 
STEP 1
    check position
    answer_1
Answers:
    answer_1: I am at STATE.position

### Go to the home position
Comes after:
Expressions: 
State changes: 
Intent: query
Program:
STEP 1
    go to home
    answer_1
Answers:
    answer_1: I am at home

### Go to the observation point for A
Comes after:
Expressions: 
State changes: 
Intent: query
Program:
STEP 1
    approach observe A
    answer_1
Answers:
    answer_1: I am at the observation point for A

### Go to P
Comes after:
Expressions:
State changes:
Intent: move
Program:
STEP 1
    go to P
    answer_1
Answers:
    answer_1: I am at P

### Visit the observation points for A and then B
Comes after:
Expressions:
State changes:
Intent: move
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1: I have visited observation points for A and B

### Prepare to pick X from empty space in A
Comes after: 
Expressions: gripper is closed, is not none, first empty in
State changes:
Intent: move
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first empty in A
    if loc is not none: 
        approach pick of X from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: Already holding something — have to drop it somewhere first.
    answer_2: Prepared to pick X from loc.
    answer_3: There is no X in A and no empty location in A.

### What is at A?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: 
        if A is empty: A is empty
        else: There is {type in loc for loc in A if loc not is not empty}

### Is there X in A?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: 
        if X not in A: No, there is no X in A
        else: Yes, there is X in loc for loc in A if X in loc

### How many slots in A are occupied?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: 
        len(loc for loc in A if loc not is empty)

### Are there any empty slots in A?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: 
        if A is empty: No, there are no empty slots in A
        if A not is empty: Yes, there are empty slots in A: loc for loc in A if loc is empty

### Which slot in A has X?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: 
        if not X in A: There is no X in A
        else: loc for loc in A if X in loc

### Which has X, A or B?
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1: 
        if not X in A and not X in B: There is no X in A or B
        else: There is {X in loc for loc in A,B if X in loc}

### Count objects by type in A
Comes after: 
Expressions:
State changes:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: There are {len(loc for loc in A if X in loc)} of X {for X in scene if X in A}

### Pick up whatever is in A
Comes after:
Expressions: gripper is closed, first occupied, is not none
State changes:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first occupied in A
    if loc is not none:
        pick from loc
        answer_2
    else: 
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: [picked(held,loc)].
    answer_3: There is no X in A.

### Pick up whatever is in A. If A is empty, pick from B instead.
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
    let loc = first occupied in A
    if loc is not none:
        pick from loc
        answer_2
    let loc = first occupied in B
    if loc is not none:
        pick from loc
        answer_3
    else:
        answer_4        
Answers:
    answer_1: [mustplace]
    answer_2: [picked(held,loc)].
    answer_3: [picked(held,loc)].
    answer_4: Both A and B are empty.

### Pick up X or W from A, whichever is there.
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let locX = first in A holding X
    let locW = first in A holding W
    if locX is not none:
        pick from locX
        answer_2
    elif locW is not none:
        pick from locW
        answer_3
    else:
        answer_4        
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc}.
    answer_3: Picked {held} from {loc}.
    answer_4: There is no X or W in A.

### Pick up whatever is at A, as long as it is not a W
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding not W
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
        
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc}.
    answer_3: 
        if A is empty: A is empty 
        else: There is nothing except W in A

### Get X from A and come back to where you started
Comes after:
Intent: pick
Program:
STEP 1
    remember start_position = check position
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        go to start_position
        answer_2
    else:
        answer_3
        
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc} and returned to {start_position}.
    answer_3: There is no X in A

### Go to A, see what's there, pick it up if it's X, then come back.
Comes after:
Intent: pick
Program:
STEP 1
    remember start_position = check position
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first in A holding X
    if loc is not none:
        pick from loc
    go to start_position
    answer_2
        
Answers:
    answer_1: [mustplace]
    answer_2: 
        if held is not none: Picked {held} from {loc} and returned to {start_position}.
        else: There is no X in A, returned to {start_postition}

### Pick up whatever is in A and bring it back.
Comes after:
Intent: pick
Program:
STEP 1
    remember start_position = check position
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    let loc = first occupied in A
    if loc is not none:
        pick from loc
    go to start_position
    answer_2
Answers:
    answer_1: [mustplace]
    answer_2: 
        if held is not none: Picked {held} from {loc} and returned to {start_position}.
        else: There is nothing in A, returned to {start_postition}

### Place what you're holding somewhere.
Comes after: [mustplace]
Intent: place
State changes:
Program:
STEP 1
    if held is unkown:
        answer_1
    elif held is none:
        answer_2
    else:
        observe everything
STEP 2
    let loc = first empty
    if loc is not none:
        place at loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: You have to tell me what I am holding first.
    answer_2: I don't hold anything.
    answer_3: Placed X in {loc}
    answer_4: There is no empty space at all.

### Place what you are holding at A
Comes after: [mustplace]
Intent: place
State changes:
Program:
STEP 1
    if held is unkown:
        answer_1
    elif held is none:
        answer_2
    else:
        observe A
STEP 2
    let loc = first empty in A
    if loc is not none:
        place at loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: You have to tell me what I am holding first.
    answer_2: I don't hold anything.
    answer_3: Placed X in {loc}.
    answer_4: There is no empty space in A.

### Place X somewhere.
Comes after: "Move X from A to B; if B is full, put X back in A": answer_1
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe everything
STEP 2
    let loc = first empty
    if loc is not none:
        place at loc
        answer_1
    else:
        answer_2
Answers:
    answer_1: Successfully placed at {loc}
    answer_2: Cannot place, no empty space found

### Place X, preferring A. If A is full, find any empty spot
Comes after:
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe A
STEP 2
    let loc = first empty in A
    if loc is not none:
        place at loc
        answer_1
    else: 
        observe everything
STEP 3
    let loc = first empty
    if loc is not none:
        place at loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: Successfully placed at {loc}
    answer_2: Successfully placed at {loc}
    answer_3: Cannot place, no empty space found

### You are holding X. Place it somewhere, but not in A
Comes after:
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe everything
STEP 2
    let loc = first empty outside A
    if loc is not none:
        place at loc
        answer_1
    else:
        answer_2
Answers:
    answer_1: Placed X at {loc}.
    answer_2: There is no empty location outside A.


### You are holding X. Place it at A, otherwise try B
Comes after:
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe A
STEP 2
    let loc = first empty in A
    if loc is not none:
        place at loc
        answer_1
    else: 
        observe B
STEP 3
    let loc = first empty in B
    if loc is not none:
        place at loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: Placed X at {loc}.
    answer_2: A was full, so I placed X at {loc}.
    answer_3: Both A and B are full — still holding X.

### You are holding X. Place it at A, only if A is completely empty
Synonyms: "Place X at A, only if A is completely empty"
Comes after:
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe A
STEP 2
    if A is not empty:
        answer_1
    let loc = first empty in A
    place at loc
    answer_2
Answers:
    answer_1: A is not empty — did not place.
    answer_2: A was empty; placed X at {loc}.

### You are holding X. Place it at A; if A has a W in it, place it at B instead
Synonyms: "Place X at A; if A has a W in it, place it at B instead" 
Comes after:
Intent: place
State changes: gripper: closed, held: X
Program:
STEP 1
    observe A
STEP 2
    if A has W:
        observe B
    else:
        let loc = first empty in A
        if loc is not none:
            place at loc
            answer_1
        else: 
            answer_2
STEP 3
    let loc = first empty in B
        if loc is not none:
            place at loc
            answer_3
        else: 
            answer_4
Answers:
    answer_1: Placed X at {loc}.
    answer_2: A has no W in it, but is full — cannot place there
    answer_3: A has W in it, placed in {loc}
    answer_4: A has W in it, but B is full - cannot place there

### Move X from A to B
Comes after:
Intent: pick+place
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    else:
    observe A
STEP 3
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        observe B
    else:
        answer_2
STEP 4
    let loc = first empty in B
    if loc is not none:
        place at loc
        answer_3
    else:    
        answer_4
Answers:
    answer_1: Already holding something — free the gripper first.
    answer_2: There is no X in A.
    answer_3: B is full.
    answer_4: Moved X to {loc}.

### Move X from A to B; if B is full, put X back in A
Comes after:
Intent: pick+place
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    else:
    observe A
STEP 3
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        observe B
    else:
        answer_2
STEP 4
    let loc = first empty in B
    if loc is not none:
        place at loc
        answer_3
STEP 5
    let loc = first empty in A
    place at loc
    answer_4

Answers:
    answer_1: Already holding something — free the gripper first.
    answer_2: There is no X in A.
    answer_3: Put X to {loc}.
    answer_4: B is full. Put X to {loc}.

### Pick whatever is at A and place it in B
Comes after:
Intent: pick+place
Program:
STEP 1
    check gripper
    observe A
STEP 2
    if gripper is closed:
        answer_1
    else:
    observe A
STEP 3
    let loc = first occupied in A
    if loc is not none:
        pick from loc
        observe B
    else:
        answer_2
STEP 4
    let loc = first empty in B
    if loc is not none:
        place at loc
        answer_3
    else:    
        answer_4
Answers:
    answer_1: Already holding something — free the gripper first.
    answer_2: A is empty.
    answer_3: B is full.
    answer_4: Moved X to {loc}.

### Find and pick up an X
Comes after:
Intent: pick
Program:
STEP 1
    check gripper
STEP 2
    if gripper is closed:
        answer_1
    else:
        observe everything
STEP 3
    let loc = first holding X
    if loc is not none:
        pick from loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: [mustplace]
    answer_2: Found and picked X from {loc}.
    answer_3: I could not find an X anywhere.

### Check what is at A; if there is an X, pick it, otherwise tell me what is there
Comes after:
Intent: pick
Program:
STEP 1
    observe A
STEP 2
    let loc = first in A holding X
    if loc is not none:
        check gripper
    else:
        answer_1
STEP 3
    if gripper is closed:
        answer_2
    else:
        let loc = first in A holding X
        pick from loc
        answer_3
Answers:
    answer_1: 
        if A not empty: There is no X in A. There is {type in loc for loc in A if loc not is not empty}. 
        else: A is empty.
    answer_2: [mustplace]
    answer_3: Picked X from {loc}. 

### Which locations in A are empty right now?
Comes after:
Expressions: 
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1:
        if A is full: There are no empty locations in A.
        else: {loc for loc in A if loc not is empty}.

### Pick up one of whatever there's most of in A
Comes after:
Features: no loc=none check
Intent: pick 
Program:
STEP 1
    check gripper
    observe A
STEP 2
    let X = most common object in A
    if gripper is closed or X is none:
        answer_1
    else:
        let loc = first in A holding X
        pick from loc
        answer_2
Answers:
    answer_1:
        if gripper is closed: [mustplace]
        else: A is empty
    answer_2: [picked(X,loc)]

### If there is an X in A, move it to B
Comes after:
Expressions: first in holding, is closed, or, ...
Intent: pick+place
Program:
STEP 1
    observe A
STEP 2
    remember loc = first in A holding X
    if loc is not none:
        check gripper
        observe B
    else:
        answer_1
STEP 3
    if gripper is closed or B is empty:
        answer_2 
    else:
        pick from loc
STEP 4
    temp loc = first empty in B
    place at loc
    answer_3
Answers:
    answer_1: There is no X in A
    answer_2: 
        if gripper is closed: There is X in A. [mustplace]
        else: There is X in A, but B is full.
    answer_3: pick

### Is A empty? If so, go home; if not, tell me what is there
Comes after:
Intent: move
Program:
STEP 1
    observe A
STEP 2
    if A is empty:
        go to home
        answer_1
    else:
        answer_2
Answers:
    answer_1: A is empty — went home.
    answer_2: A contains: {occupied slots in A}.

### You are holding X. Place it at A; report whether A is then full
Comes after:
Intent: place
Program:
STEP 1
    observe A
STEP 2
    if A is full:
        answer_1
    let last = count of empty slots in A == 1
    let loc = first empty in A
    place at loc
    if last:
        answer_2
    else:
        answer_3
Answers:
    answer_1: A is already full — could not place.
    answer_2: Placed X at {loc}; A is now full.
    answer_3: Placed X at {loc}; A still has room.

### Check A and B; pick the X from whichever has it
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
    let loc = first in A holding X
    if loc is not none:
        pick from loc
        answer_2
    let loc = first in B holding X
    if loc is not none:
        pick from loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: [mustplace]
    answer_2: Picked X from {loc} in A.
    answer_3: Picked X from {loc} in B.
    answer_4: Neither A nor B has an X.

### Compare A and B; if both have an X, pick from A
Comes after:
Intent: pick
Same program as "Check A and B; pick the X from whichever has it" — the A branch is tested first, so it wins when both have an X. (Covers old Tasks 44 and 46.)

### Check A and B; pick from whichever is not empty
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
    let loc = first occupied in A
    if loc is not none:
        pick from loc
        answer_2
    let loc = first occupied in B
    if loc is not none:
        pick from loc
        answer_3
    else:
        answer_4
Answers:
    answer_1: [mustplace]
    answer_2: Picked {held} from {loc} in A.
    answer_3: Picked {held} from {loc} in B.
    answer_4: Both A and B are empty.

### You are holding X. Place it in whichever of A or B has more room
Comes after:
Intent: place
Program:
STEP 1
    observe A
    observe B
STEP 2
    if A is full and B is full:
        answer_1
    if more empty room in A than B:
        let loc = first empty in A
        place at loc
        answer_2
    else:
        let loc = first empty in B
        place at loc
        answer_3
Answers:
    answer_1: Both A and B are full — still holding X.
    answer_2: A has more room; placed X at {loc}.
    answer_3: Placed X at {loc} in B.

### You are holding something. If it is an X place it at A; if it is a W place it at B
Comes after:
Intent: place
Program:
STEP 1
    if holding X:
        observe A
    elif holding W:
        observe B
    else:
        answer_1
STEP 2
    if holding X:
        let loc = first empty in A
    elif holding W:
        let loc = first empty in B
    if loc is not none:
        place at loc
        answer_2
    else:
        answer_3
Answers:
    answer_1: I am holding something else — neither an X nor a W.
    answer_2: Placed it at {loc}.
    answer_3:
        if holding X: A is full — still holding X.
        else: B is full — still holding W.

### You are holding X. Place it somewhere, then go home
Comes after:
Intent: place
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
    answer_1: Placed X at {loc}, then went home.
    answer_2: Found no empty location; went home still holding X.

### You are holding W. Drop it at A, then bring an X back to where you started
Comes after:
Intent: move
Program:
STEP 1
    remember start_position = check position
    observe everything
STEP 2
    let loc = first empty in A
    if loc is none:
        answer_1
    place at loc
STEP 3
    let loc = first holding X
    if loc is not none:
        pick from loc
        go to start_position
        answer_2
    else:
        go to start_position
        answer_3
Answers:
    answer_1: A is full — cannot drop W; did nothing.
    answer_2: Dropped W at A, picked up an X, and returned to {start_position}.
    answer_3: Dropped W at A, but found no X anywhere; returned to {start_position}.

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

### How many X are in A?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: There are {count of X in A} X in A.

### How many empty locations are there in A?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    answer_1
Answers:
    answer_1: There are {count of empty slots in A} empty locations in A.

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

### Are there more objects in A or B?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1:
        if count in A > count in B: A has more objects.
        elif count in B > count in A: B has more objects.
        else: A and B have the same number of objects.

### Do A and B have the same number of objects?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1:
        if same count in A and B: Yes, A and B have the same number of objects.
        else: No, they hold different numbers of objects.

### Does A have more X than B?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1:
        if count of X in A > count of X in B: Yes, A has more X than B.
        else: No, A does not have more X than B.

### How many X are there in total across A and B?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1: There are {count of X in A + count of X in B} X across A and B.

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

### How many objects are there in total across A and B?
Comes after:
Intent: query
Program:
STEP 1
    observe A
    observe B
    answer_1
Answers:
    answer_1: There are {count in A + count in B} objects across A and B.

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
Intent: place
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

Answers:
    [mustplace]: Already holding something — can't pick.
    [picked(X,loc)]: Picked {X} from {loc}.
    [placed(X,loc)]: Placed {X} into {loc}.