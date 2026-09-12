# The GitHub tab: menu with the contribution graph, review inbox, a pull request, its diff,
# and pushed branches. Record from the repo root: vhs demo/github.tape

Output demo/recordings/github.gif

Set Shell "bash"
Set FontSize 15
Set Width 1300
Set Height 800
Set Padding 20
Set Theme "Catppuccin Mocha"
Set Framerate 24

# Only the shim is hidden, so the visible command is the one a real user types.
Hide
Type "smorg() { uv run demo/run.py github; }"
Enter
Type "clear"
Enter
Show

Sleep 1s
Type "smorg"
Sleep 800ms
Enter

# Startup: the octocat and the bar while it connects, then the menu with a year of contributions.
Sleep 11s

# The review inbox: what is waiting on you, then what you are waiting on.
Enter
Sleep 5s

# Down to the last pull request, a beat, then back up to the top.
Down@70ms 9
Sleep 2s
Up@70ms 9
Sleep 2s

# One pull request, full screen.
Enter
Sleep 4s

# Read down its description and the review conversation, then back to the top.
Down@60ms 12
Sleep 2s
Up@60ms 12
Sleep 2s

# Its diff: the file list on the left, the patch beside it.
Enter
Sleep 4s
Type "j"
Sleep 2s
Type "j"
Sleep 3s
Escape
Sleep 2s
Escape
Sleep 2s

# Back to the menu, then across to branches pushed with no pull request yet.
Escape
Sleep 2s
Down
Sleep 1s
Enter
Sleep 4s
Down@70ms 4
Sleep 2s
Up@70ms 4
Sleep 2s

Escape
Sleep 2s
