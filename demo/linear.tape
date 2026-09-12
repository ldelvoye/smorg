# The Linear tab: startup, issue list, issue page, navigation, projects, project issues.
# Record from the repo root: vhs demo/linear.tape

Output demo/recordings/linear.gif

Set Shell "bash"
Set FontSize 15
Set Width 1300
Set Height 800
Set Padding 20
Set Theme "Catppuccin Mocha"
Set Framerate 24

# Only the shim is hidden, so the visible command is the one a real user types.
Hide
Type "smorg() { uv run demo/run.py linear; }"
Enter
Type "clear"
Enter
Show

Sleep 1s
Type "smorg"
Sleep 800ms
Enter

# Startup: the loading art while it connects, then the mark draws in under the sky and shines
# because changes are waiting.
Sleep 11s

# The issue list: status groups, discs and priority bars. The selected title is too long for
# the row, so it slides sideways on its own.
Enter
Sleep 5s

# Down to the last issue, a beat, then back up to the top.
Down@70ms 15
Sleep 2s
Up@70ms 15
Sleep 2s

# An issue, full screen: reading column, properties sidebar, breadcrumb.
Enter
Sleep 4s

# Read down the description and the activity below it, then back to the top.
Down@60ms 12
Sleep 2s
Up@60ms 12
Sleep 2s

# Open something related from here, then walk back through the trail.
Enter
Sleep 3s
Down
Sleep 1s
Enter
Sleep 3s
Backspace
Sleep 3s
Escape
Sleep 1s

# Back out to the menu, then across to projects.
Escape
Sleep 1s
Escape
Sleep 1s
Escape
Sleep 2s
Down
Sleep 1s
Enter
Sleep 4s

# A project page: description, milestones with progress bars, issue counts.
Enter
Sleep 4s
Down@60ms 12
Sleep 2s
Up@60ms 12
Sleep 2s

# Its issues: status groups with the sub-issue tree and the assignee column.
Enter
Sleep 3s
Down@70ms 12
Sleep 2s
Up@70ms 12
Sleep 2s

Escape
Sleep 1s
Escape
Sleep 2s
