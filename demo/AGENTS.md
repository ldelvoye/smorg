# Recording demo tapes

How the gifs in this repo get made. Read this before writing or changing a `.tape`.

The recordings run against invented data from `linear_data.py` and `github_data.py`, never a real
workspace. Nothing here reaches the network: `harness.py` substitutes a demo integration whose
`fetch` returns a fixed list, and points the config directory and credential store at a scratch
directory. A recording can therefore never leak a real ticket, branch, or colleague.

`DATA_NOTES.md` maps every part of the two datasets to the feature it exists to exercise. Read it
before changing the data, and keep it true afterwards: a tape's route depends on what the data
holds, so thinning a dataset quietly breaks a recording.

## Rules

These are the ones that exist so far. Expect more.

**1. Show the launch, and land on the subject.** A tape starts at a shell prompt and types
`smorg`, so the recording includes the startup: the loading art while it connects, and whatever
the tab draws on arrival. Do not hide the boot to save seconds; those seconds are the product.

What is hidden is one line defining a `smorg` shell function that points at `run.py`, so the
command on screen is the one a real user types rather than the harness path. That is the only
thing a tape may hide.

When the app comes up, the tab the gif is about must already be in front. A viewer never watches
someone navigate to the subject. Tab order is the order passed to `run.py` and the first tab is
active, so this is a matter of naming the subject first. A tape covering several integrations at
once may order them however it likes.

**2. Scroll, and scroll quickly.** A list that never moves reads as a screenshot. Run the cursor
down at roughly 70ms a step, stop on the last row for a beat, then run it back up. Stop one short
of the count: the cursor wraps, and a jump from the bottom straight back to the top reads as a
glitch rather than as navigation.

**3. Scroll the long text too, not just the lists.** Every tape reads down at least one issue or
pull request description and one project description, then returns to the top. A page that only
ever shows its first screen leaves a viewer thinking that is all there is. The reading column
takes the arrow keys once the page has focus, so this needs no extra keys.

A recording shows what someone who installed smorg sees, not what a developer running from a
checkout sees. `harness.py` already turns the dev badge off for that reason. Anything else that
only appears in a working copy should go the same way, and be noted here when it does.

## Running one

```
uv run demo/run.py linear          # one tab, active on boot
uv run demo/run.py github linear   # two tabs, github active
```

## Recording one

```
vhs demo/linear.tape
```

Each tape writes its gif to `recordings/` beside it, named after the tape. Keep the terminal size,
font and theme identical across tapes so the gifs sit together on a page without jumping.

`recordings/` is git-ignored. The gifs are build output, attached to release notes rather than
carried in the repository, so re-recording freely costs nothing and no stale copy can survive in
the history. Record the ones you need, attach them, and leave them behind.

## Weight

A gif's size tracks how many pixels change and for how long, not the framerate. Measured on the
Linear tape: dropping from 24 frames a second to 12 saved nothing at all, and a 64-colour palette
only went from 12MB to 9MB. What costs is duration times motion, and the two expensive things
here are the starry sky, which repaints continuously, and fast scrolling, which redraws the whole
screen every step. If a recording needs to be lighter, shorten it or make the window smaller.
Reaching for the framerate is wasted effort.

## Writing one

The app animates, and animation needs room. The sky, the mark's draw-in and its shine are all
driven by elapsed time rather than by keystrokes, so a tape that types continuously records a
UI mid-stride and looks broken. Leave a `Sleep` wherever something is meant to be looked at.

Drive the app only through keys a user has: the tape is a demonstration, not a test harness.
If a feature cannot be reached by keystrokes, that is worth knowing and worth saying, rather
than working around inside the tape.
