# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
# NeuroShell Fish Semantic Shell Integration

if set -q NEUROSHELL_SHELL_INTEGRATION_ACTIVE
    exit 0
end
set -gx NEUROSHELL_SHELL_INTEGRATION_ACTIVE 1

function __neuroshell_postexec --on-event fish_postexec
    set -l exit_code $status
    printf "\033]133;D;%s\007" "$exit_code"
    printf "\033]7;file://%s%s\007" (hostname) "$PWD"
end

function __neuroshell_preexec --on-event fish_preexec
    printf "\033]133;C\007"
end

function z
    if test (count $argv) -eq 0
        neuroshell z
    else
        set -l dest (neuroshell --get-jump "$argv")
        if test -n "$dest" -a -d "$dest"
            cd "$dest"
        else
            builtin cd $argv
        end
    end
end
