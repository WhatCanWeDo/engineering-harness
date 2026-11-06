on run argv
    set delimiter to character id 9
    if application "Ghostty" is not running then error "Ghostty is not running"
    tell application "Ghostty"
        if item 1 of argv is "inventory" then
            set output to ""
            repeat with w in windows
                repeat with t in tabs of w
                    repeat with term in terminals of t
                        set output to output & (id of w) & delimiter & (id of t) & delimiter & (id of term) & delimiter & (tty of term) & linefeed
                    end repeat
                end repeat
            end repeat
            return output
        end if
        set operation to item 1 of argv
        if operation is not "open" and operation is not "decorate" then error "Unknown operation"
        set sourceTerminalID to item 2 of argv
        -- Window IDs and returned object specifiers can become stale when macOS
        -- converts a single window into a native tab group. Resolve by terminal.
        repeat with w in windows
            repeat with t in tabs of w
                repeat with term in terminals of t
                    if id of term is sourceTerminalID then
                        if operation is "decorate" then
                            set name override of t to item 3 of argv
                            select tab t
                            return "decorated"
                        end if
                        set cfg to new surface configuration
                        set initial working directory of cfg to item 3 of argv
                        set command of cfg to item 4 of argv
                        set wait after command of cfg to true
                        new tab in w with configuration cfg
                        -- Never dereference w or the returned tab after mutation.
                        return "created"
                    end if
                end repeat
            end repeat
        end repeat
        error "Ghostty terminal no longer exists"
    end tell
end run
