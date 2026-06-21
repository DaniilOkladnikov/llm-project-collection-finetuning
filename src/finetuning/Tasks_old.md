### Task 1 — Pick up the $X from $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed:
    answer "already holding something"
  otherwise:
    observe $Y
STEP 3:
  when $Y has $X:
    pick $X from (first in $Y holding $X)
    answer "picked $X from $Y"
  otherwise:
    answer "no $X in $Y"
```

### Task 2 — Place the $X into $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    answer "not holding anything"
  otherwise:
    observe $Y
STEP 3:
  when $Y is full:
    answer "$Y has no empty slot"
  otherwise:
    place at (first empty in $Y)
    answer "placed $X into $Y"
```

### Task 3 — What am I holding?

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    answer "nothing — gripper is open"
  when held is known:
    answer "holding " + held
  otherwise:
    answer "gripper is closed, content unknown"
```

### Task 4 — Am I holding a $X?

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    answer "no — gripper is open"
  when holding $X:
    answer "yes"
  otherwise:
    answer "no — holding something else or unknown"
```

### Task 5 — Is my gripper free?

```
STEP 1: check gripper
STEP 2: answer (gripper is open)
```

### Task 6 — What position am I at?

```
STEP 1: check position
STEP 2: answer position
```

### Task 7 — Go to the home position.

```
STEP 1:
  go home
  answer "at home"
```

### Task 8 — Go to the observation position for $Y.

```
STEP 1:
  go observe $Y
  answer "at observation position for $Y"
```

### Task 9 — Visit the observation points for $Y and then $Z.

```
STEP 1:
  go observe $Y
  go observe $Z
  answer "visited observation points for $Y and $Z"
```

### Task 10 — Go to the pick position for $X at $Y, do not pick.

```
STEP 1:
  approach pick of $X at $Y
  answer "at pick position for $X at $Y"
```

### Task 11 — What is at $Y?

```
STEP 1: observe $Y
STEP 2: answer (occupied slots in $Y)
```

### Task 12 — Is there a $X at $Y?

```
STEP 1: observe $Y
STEP 2: answer ($Y has $X)
```

### Task 13 — List all objects in $Y.

```
STEP 1: observe $Y
STEP 2: answer (occupied slots in $Y)
```

### Task 14 — How many slots in $Y are occupied?

```
STEP 1: observe $Y
STEP 2: answer (count in $Y)
```

### Task 15 — Are there any empty slots in $Y?

```
STEP 1: observe $Y
STEP 2: answer (not $Y is full)
```

### Task 16 — Which slot in $Y has the $X?

```
STEP 1: observe $Y
STEP 2: answer (first in $Y holding $X)
```

### Task 17 — Which has $X: $Y or $Z?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2:
  when $Y has $X and $Z has $X: answer "both"
  when $Y has $X: answer "$Y"
  when $Z has $X: answer "$Z"
  otherwise: answer "neither"
```

### Task 18 — Count objects by type in $Y.

```
STEP 1: observe $Y
STEP 2: answer (for every t in types in $Y: t + " = " + count of t in $Y)
```

### Task 19 — Pick up whatever is at $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed:
    answer "already holding something"
  otherwise:
    observe $Y
STEP 3:
  when $Y is empty:
    answer "nothing at $Y"
  otherwise:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    answer "picked " + obj
```

### Task 20 — Pick up whatever is at $Y. If $Y is empty, pick from $Z instead.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y is not empty:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    answer "picked " + obj + " from $Y"
  otherwise when $Z is not empty:
    remember (L, obj) = first occupied in $Z
    pick whatever is at L
    answer "picked " + obj + " from $Z"
  otherwise:
    answer "both $Y and $Z are empty"
```

### Task 21 — Pick up a $X or a $W from $Y, whichever is there.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y has $X:
    pick $X from (first in $Y holding $X)
    answer "picked $X"
  otherwise when $Y has $W:
    pick $W from (first in $Y holding $W)
    answer "picked $W"
  otherwise:
    answer "neither $X nor $W in $Y"
```

### Task 22 — Pick up whatever is at $Y, as long as it is not a $W.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y is empty: answer "nothing at $Y"
  otherwise:
    remember (L, obj) = first occupied in $Y
    when obj is $W: answer "only $W at $Y — skipping"
    otherwise:
      pick whatever is at L
      answer "picked " + obj
```

### Task 23 — Get the $X from $Y and come back to where you started.

```
STEP 1:
  check gripper
  check position
STEP 2:
  remember start = position
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y has $X:
    pick $X from (first in $Y holding $X)
    go to start
    answer "returned to start with $X"
  otherwise:
    go to start
    answer "no $X in $Y, returned to start"
```

### Task 24 — Go to $Y, see what's there, pick it up if it's a $X, then come back.

```
STEP 1:
  check gripper
  check position
STEP 2:
  remember start = position
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y is empty:
    go to start
    answer "$Y was empty, returned"
  otherwise:
    remember (L, obj) = first occupied in $Y
    when obj is $X:
      pick $X from L
      go to start
      answer "picked $X, returned"
    otherwise:
      go to start
      answer "found " + obj + ", not $X — returned"
```

### Task 25 — Pick up whatever is at $Y and bring it back.

```
STEP 1:
  check gripper
  check position
STEP 2:
  remember start = position
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y is empty:
    go to start
    answer "nothing at $Y"
  otherwise:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    go to start
    answer "picked " + obj + ", returned"
```

### Task 26 — Place the $X somewhere.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    remember candidates = all known collections
STEP 3 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 4:
  when some candidate has empty:
    place at (first empty in first candidate with empty)
    answer "placed $X"
  otherwise:
    answer "no empty slot anywhere"
```

### Task 27 — Place the $X, preferring $Y. If $Y is full, find any empty spot.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y is not full:
    place at (first empty in $Y)
    answer "placed in $Y"
  otherwise:
    remember candidates = all known collections other than $Y
STEP 4 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 5:
  when some candidate has empty:
    place at (first empty in first candidate with empty)
    answer "placed elsewhere — $Y was full"
  otherwise:
    answer "$Y full and nowhere else has space"
```

### Task 28 — Place the $X somewhere, but not at $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    remember candidates = all known collections other than $Y
STEP 3 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 4:
  when some candidate has empty:
    place at (first empty in first candidate with empty)
    answer "placed (not in $Y)"
  otherwise:
    answer "no empty slot outside $Y"
```

### Task 29 — Put the $X at $Y if possible, otherwise anywhere.

Same program as Task 27.

### Task 30 — Place $X at $Y, if occupied try $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y is not full:
    place at (first empty in $Y)
    answer "placed in $Y"
  otherwise when $Z is not full:
    place at (first empty in $Z)
    answer "$Y was full, placed in $Z"
  otherwise:
    answer "both $Y and $Z are full"
```

### Task 31 — Place $X at $Y, but only if $Y is completely empty. Do not try elsewhere.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y is empty:
    place at (first empty in $Y)
    answer "placed — $Y was empty"
  otherwise:
    answer "$Y is not empty"
```

### Task 32 — Place $X at $Y. If $Y has a $W in it, place at $Z instead.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has $W:
    when $Z is full: answer "$Y has $W and $Z is full"
    otherwise:
      place at (first empty in $Z)
      answer "placed in $Z ($Y had a $W)"
  otherwise:
    when $Y is full: answer "$Y is full and has no $W"
    otherwise:
      place at (first empty in $Y)
      answer "placed in $Y"
```

### Task 33 — Move the $X from $Y to $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has no $X: answer "no $X in $Y"
  otherwise when $Z is full: answer "$Z is full"
  otherwise:
    pick $X from (first in $Y holding $X)
    place at (first empty in $Z)
    answer "moved $X from $Y to $Z"
```

### Task 34 — Move the $X from $Y to $Z. If $Z is occupied, bring $X back to $Y.

(Interpreting `$Z is occupied` as `$Z is full`.)

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has no $X: answer "no $X in $Y"
  otherwise:
    remember source = first in $Y holding $X
    pick $X from source
    when $Z is full:
      place at source
      answer "$Z was full — returned $X to $Y"
    otherwise:
      place at (first empty in $Z)
      answer "moved $X to $Z"
```

### Task 35 — Pick whatever is at $Y and place it in $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y is empty: answer "nothing at $Y"
  otherwise when $Z is full: answer "$Z is full"
  otherwise:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    place at (first empty in $Z)
    answer "moved " + obj + " from $Y to $Z"
```

### Task 36 — Find and pick up a $X.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    remember candidates = all known collections
STEP 3 (repeat until):
  repeat until (some candidate has $X) or (candidates exhausted):
    observe (next in candidates)
STEP 4:
  when some candidate has $X:
    remember source = first candidate with $X
    pick $X from (first in source holding $X)
    answer "picked $X from " + source
  otherwise:
    answer "no $X found"
```

### Task 37 — Check what is at $Y. If there's $X, pick it up. Otherwise, just tell me what you found.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y is empty: answer "$Y is empty"
  otherwise when $Y has $X:
    pick $X from (first in $Y holding $X)
    answer "picked $X"
  otherwise:
    answer "$Y contains " + (occupied slots in $Y)
```

### Task 38 — Which locations in $Y do not have any objects right now?

```
STEP 1: observe $Y
STEP 2: answer (empty slots in $Y)
```

### Task 39 — Place what I'm holding at $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y is full: answer "$Y is full"
  otherwise:
    place at (first empty in $Y)
    answer "placed"
```

### Task 40 — If there's $X in $Y, move it to $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has no $X: answer "no $X in $Y"
  otherwise when $Z is full: answer "$Z is full"
  otherwise:
    pick $X from (first in $Y holding $X)
    place at (first empty in $Z)
    answer "moved $X to $Z"
```

### Task 41 — Is $Y empty? If so, go home. If not, tell me what's there.

```
STEP 1: observe $Y
STEP 2:
  when $Y is empty:
    go home
    answer "$Y empty — went home"
  otherwise:
    answer (occupied slots in $Y)
```

### Task 42 — Place your object at $Y. Report if $Y is then full.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y is full: answer "$Y already full — couldn't place"
  otherwise:
    remember after_place_fills = (count in $Y + 1 == size of $Y)
    place at (first empty in $Y)
    when after_place_fills: answer "placed — $Y is now full"
    otherwise: answer "placed — $Y still has room"
```

### Task 43 — Check $Y and $Z. Pick from whichever has it ($X).

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has $X:
    pick $X from (first in $Y holding $X)
    answer "picked $X from $Y"
  otherwise when $Z has $X:
    pick $X from (first in $Z holding $X)
    answer "picked $X from $Z"
  otherwise:
    answer "neither has $X"
```

### Task 44 — Compare $Y and $Z. If both have $X, pick from $Y.

Same program as Task 43 (when both have $X, the `$Y` branch fires first).

### Task 45 — Check $Y and $Z. Pick from whichever isn't empty.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y is not empty:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    answer "picked " + obj + " from $Y"
  otherwise when $Z is not empty:
    remember (L, obj) = first occupied in $Z
    pick whatever is at L
    answer "picked " + obj + " from $Z"
  otherwise:
    answer "both empty"
```

### Task 46 — Same as Task 44.

### Task 47 — Check $Y and $Z. Place what you're holding to where there's more room.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y is full and $Z is full: answer "both full"
  otherwise when more room in $Y than $Z:
    when $Y is full: answer "$Y is full"
    otherwise:
      place at (first empty in $Y)
      answer "placed in $Y (more room)"
  otherwise:
    when $Z is full: answer "$Z is full"
    otherwise:
      place at (first empty in $Z)
      answer "placed in $Z (more room)"
```

### Task 48 — If you hold $X, place it at $Y. If you hold $W, place it at $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  when holding $X: observe $Y
  when holding $W: observe $Z
  otherwise: answer "holding something else"
STEP 3:
  when holding $X:
    when $Y is full: answer "$Y is full"
    otherwise:
      place at (first empty in $Y)
      answer "placed $X at $Y"
  when holding $W:
    when $Z is full: answer "$Z is full"
    otherwise:
      place at (first empty in $Z)
      answer "placed $W at $Z"
```

### Task 49 — If you're not holding anything, go home. Otherwise, place it and then go home.

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    go home
    answer "not holding — went home"
  otherwise:
    remember candidates = all known collections
STEP 3 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 4:
  when some candidate has empty:
    place at (first empty in first candidate with empty)
    go home
    answer "placed and went home"
  otherwise:
    go home
    answer "couldn't place anywhere — went home still holding"
```

### Task 50 — Bring $X to where you are. If gripper is occupied, drop load at $Y first.

```
STEP 1:
  check gripper
  check position
STEP 2:
  remember here = position
  when gripper is closed:
    observe $Y
  otherwise:
    remember candidates = all known collections
STEP 3:
  when gripper was closed:
    when $Y is full:
      answer "$Y is full — can't drop load"
    otherwise:
      place at (first empty in $Y)
      remember candidates = all known collections
STEP 4 (repeat until):
  repeat until (some candidate has $X) or (candidates exhausted):
    observe (next in candidates)
STEP 5:
  when some candidate has $X:
    pick $X from (first slot with $X across candidates)
    go to here
    answer "brought $X here"
  otherwise:
    go to here
    answer "no $X found — came back empty-handed"
```

### Task 51 — If $Y has $X, pick it; otherwise just go home.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y has $X:
    pick $X from (first in $Y holding $X)
    answer "picked $X"
  otherwise:
    go home
    answer "no $X in $Y — went home"
```

### Task 52 — Am I at home?

```
STEP 1: check position
STEP 2: answer (position is home)
```

### Task 53 — Is $Y empty?

```
STEP 1: observe $Y
STEP 2: answer ($Y is empty)
```

### Task 54 — Is $Y full?

```
STEP 1: observe $Y
STEP 2: answer ($Y is full)
```

### Task 55 — How many $X are in $Y?

```
STEP 1: observe $Y
STEP 2: answer (count of $X in $Y)
```

### Task 56 — How many empty locations are there in $Y?

```
STEP 1: observe $Y
STEP 2: answer (size of empty slots in $Y)
```

### Task 57 — Is there anything other than $X in $Y?

```
STEP 1: observe $Y
STEP 2: answer (any in $Y other than $X is not none)
```

### Task 58 — Are there more objects in $Y or $Z?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2:
  when count in $Y > count in $Z: answer "$Y"
  when count in $Z > count in $Y: answer "$Z"
  otherwise: answer "equal"
```

### Task 59 — Do $Y and $Z have the same number of objects?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer (same count in $Y and $Z)
```

### Task 60 — Does $Y have more $X than $Z?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer (count of $X in $Y > count of $X in $Z)
```

### Task 61 — How many $X are there in total across $Y and $Z?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer (count of $X in $Y + count of $X in $Z)
```

### Task 62 — List all $X entities you can find.

```
STEP 1: observe everything
STEP 2: answer (every L where contents at L is $X)
```

### Task 63 — Are $Y and $Z both empty?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer ($Y is empty and $Z is empty)
```

### Task 64 — Is either $Y or $Z empty?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer ($Y is empty or $Z is empty)
```

### Task 65 — How many objects are there in total across $Y and $Z?

```
STEP 1:
  observe $Y
  observe $Z
STEP 2: answer (count in $Y + count in $Z)
```

### Task 66 — Go to $Y, then come back to where you started.

```
STEP 1: check position
STEP 2:
  remember here = position
  go observe $Y
  go to here
  answer "visited $Y and returned"
```

### Task 67 — Pick up an object at $Y that isn't $X.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  remember hit = any in $Y other than $X
  when hit is none: answer "$Y only has $X or is empty"
  otherwise:
    remember (L, obj) = hit
    pick whatever is at L
    answer "picked " + obj
```

### Task 68 — Pick the only object in $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when count in $Y == 1:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    answer "picked " + obj
  otherwise:
    answer "$Y does not have exactly one object"
```

### Task 69 — Pick from $Y the same object that is in $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Z is empty: answer "$Z is empty"
  otherwise:
    remember (_, target_obj) = first occupied in $Z
    when $Y has target_obj:
      pick target_obj from (first in $Y holding target_obj)
      answer "picked " + target_obj
    otherwise:
      answer "$Y has no " + target_obj
```

### Task 70 — Pick up from $Y something that also is present in $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  remember shared = types shared by $Y and $Z
  when shared is empty: answer "no overlapping type"
  otherwise:
    remember t = any member of shared
    pick t from (first in $Y holding t)
    answer "picked " + t
```

### Task 71 — Pick up from $Y something that isn't present in $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  remember unique = types in $Y but not $Z
  when unique is empty: answer "every type in $Y is also in $Z"
  otherwise:
    remember t = any member of unique
    pick t from (first in $Y holding t)
    answer "picked " + t
```

### Task 72 — Place what you're holding at $Y if it's not $X. If it's $X, place at $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  when holding $X: observe $Z
  otherwise: observe $Y
STEP 3:
  when holding $X:
    when $Z is full: answer "$Z is full"
    otherwise:
      place at (first empty in $Z)
      answer "placed $X at $Z"
  otherwise:
    when $Y is full: answer "$Y is full"
    otherwise:
      place at (first empty in $Y)
      answer "placed at $Y"
```

### Task 73 — Pick from $Y if $Y has at least $N objects.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when count in $Y >= $N:
    remember (L, obj) = first occupied in $Y
    pick whatever is at L
    answer "picked " + obj
  otherwise:
    answer "$Y has fewer than $N objects"
```

### Task 74 — Pick from $Y only if everything there is an $X.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y is empty: answer "$Y is empty"
  when types in $Y == { $X }:
    pick $X from (first in $Y holding $X)
    answer "picked $X"
  otherwise:
    answer "$Y contains something other than $X"
```

### Task 75 — Check $Y. If it has $X, pick something from $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has no $X: answer "$Y has no $X"
  otherwise when $Z is empty: answer "$Z is empty"
  otherwise:
    remember (L, obj) = first occupied in $Z
    pick whatever is at L
    answer "picked " + obj + " from $Z"
```

### Task 76 — Place your load at $Y. If there already is this type in $Y, place at $Z.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has held:
    when $Z is full: answer "$Y has this type, $Z is full"
    otherwise:
      place at (first empty in $Z)
      answer "placed at $Z (same type present in $Y)"
  otherwise:
    when $Y is full: answer "$Y is full"
    otherwise:
      place at (first empty in $Y)
      answer "placed at $Y"
```

### Task 77 — Place your load at $Y, if there isn't already this type in $Y.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y has held: answer "$Y already has this type"
  otherwise when $Y is full: answer "$Y is full"
  otherwise:
    place at (first empty in $Y)
    answer "placed at $Y"
```

### Task 78 — If you're holding anything, put it down first. Then get $X.

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    remember find_candidates = all known collections
  otherwise:
    remember drop_candidates = all known collections
STEP 3 (repeat until):     // drop phase, only runs if we were holding
  when gripper was closed:
    repeat until (some drop candidate has empty) or (drop_candidates exhausted):
      observe (next in drop_candidates)
STEP 4:
  when gripper was closed:
    when some drop candidate has empty:
      place at (first empty in first drop candidate with empty)
      remember find_candidates = all known collections
    otherwise:
      answer "nowhere to drop — aborting"
STEP 5 (repeat until):     // find phase
  repeat until (some find candidate has $X) or (find_candidates exhausted):
    observe (next in find_candidates)
STEP 6:
  when some find candidate has $X:
    pick $X from (first slot with $X across find_candidates)
    answer "dropped (if needed) and picked $X"
  otherwise:
    answer "no $X found"
```

### Task 79 — Place the load at $Y. If $Y is full, hold it.

```
STEP 1: check gripper
STEP 2:
  when gripper is open: answer "not holding anything"
  otherwise: observe $Y
STEP 3:
  when $Y is full: answer "$Y is full — keeping the load"
  otherwise:
    place at (first empty in $Y)
    answer "placed at $Y"
```

### Task 80 — Find any empty location and report.

```
STEP 1:
  remember candidates = all known collections
STEP 2 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 3:
  when some candidate has empty:
    answer "empty at " + (first empty in first candidate with empty)
  otherwise:
    answer "no empty location anywhere"
```

### Task 81 — Find an $X. If it's at $Y, move it to $Z. Otherwise leave it.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise:
    observe $Y
    observe $Z
STEP 3:
  when $Y has no $X: answer "$X is not at $Y — leaving it"
  otherwise when $Z is full: answer "$Z is full"
  otherwise:
    pick $X from (first in $Y holding $X)
    place at (first empty in $Z)
    answer "moved $X from $Y to $Z"
```

### Task 82 — Can you now pick something from $Y?

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "no — holding something"
  otherwise: observe $Y
STEP 3: answer ($Y is not empty)
```

### Task 83 — Pick $X from $Y. Then tell me what $Y has left.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  when $Y has no $X: answer "no $X in $Y"
  otherwise:
    remember source = first in $Y holding $X
    pick $X from source
    answer "picked $X. $Y still has: " + (occupied slots in $Y minus source)
```

### Task 84 — Tell me what is at $Y and then pick up $X from there.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "already holding"
  otherwise: observe $Y
STEP 3:
  remember snapshot = occupied slots in $Y
  when $Y has no $X: answer "$Y contains " + snapshot + ". No $X."
  otherwise:
    pick $X from (first in $Y holding $X)
    answer "$Y contained " + snapshot + ". Picked $X."
```

### Task 85 — Ensure there is an $X at $Y.

See Walkthrough C, §9.3.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "free the gripper first"
  otherwise: observe $Y
STEP 3:
  when $Y has $X: answer "$Y already has $X"
  otherwise when $Y is full: answer "$Y has no room for $X"
  otherwise:
    remember target = first empty in $Y
    remember candidates = all known collections other than $Y
STEP 4 (repeat until):
  repeat until (some candidate has $X) or (candidates exhausted):
    observe (next in candidates)
STEP 5:
  when some candidate has $X:
    pick $X from (first slot with $X across candidates)
    place at target
    answer "moved $X into $Y"
  otherwise:
    answer "no $X exists anywhere reachable"
```

### Task 86 — Ensure $Y is empty.

```
STEP 1: check gripper
STEP 2:
  when gripper is closed: answer "free the gripper first"
  otherwise:
    observe $Y
    observe everything
STEP 3:
  when $Y is empty: answer "$Y is already empty"
  when (size of occupied slots in $Y) > (count of empty slots outside $Y):
    answer "not enough room outside $Y to evacuate it"
  otherwise:
    for every (L, obj) in occupied slots in $Y:
      pick whatever is at L
      place at (next empty slot outside $Y)
    answer "$Y is now empty"
```

### Task 87 — Empty the gripper and move to home.

```
STEP 1: check gripper
STEP 2:
  when gripper is open:
    go home
    answer "gripper already empty — at home"
  otherwise:
    remember candidates = all known collections
STEP 3 (repeat until):
  repeat until (some candidate has empty) or (candidates exhausted):
    observe (next in candidates)
STEP 4:
  when some candidate has empty:
    place at (first empty in first candidate with empty)
    go home
    answer "placed load, at home"
  otherwise:
    go home
    answer "nowhere to place — went home still holding"
```

---

## Appendix — Quick-reference cheatsheet

**Start every program** with `check gripper` *if and only if* the task's
correctness depends on gripper state that isn't already in `STATE`.

**Never** split `observe $Y; observe $Z` into two steps when both
results are needed together for the next decision.

**Always** put a `repeat until` in its own step, and write its
termination condition so it references state the body updates.

**Prefer** up-front scans of all targets a decision depends on, even
when some branches won't use them — saves a whole step.

**Use memory** only for values that cross step boundaries or require
recomputation that the LLM cannot cheaply redo from scans.
