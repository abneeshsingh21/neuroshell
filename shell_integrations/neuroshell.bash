# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
# NeuroShell Bash Semantic Shell Integration

if [[ -n "$NEUROSHELL_SHELL_INTEGRATION_ACTIVE" ]]; then
    return
fi
export NEUROSHELL_SHELL_INTEGRATION_ACTIVE=1

neuroshell_precmd() {
    local exit_code=$?
    printf "\033]133;D;%s\007" "$exit_code"
    printf "\033]7;file://%s%s\007" "$HOSTNAME" "$PWD"
    printf "\033]133;A\007"
}

# Chain into PROMPT_COMMAND
if [[ -z "$PROMPT_COMMAND" ]]; then
    PROMPT_COMMAND="neuroshell_precmd"
else
    PROMPT_COMMAND="neuroshell_precmd; $PROMPT_COMMAND"
fi

z() {
    if [[ $# -eq 0 ]]; then
        neuroshell z
    else
        local dest
        dest=$(neuroshell --get-jump "$*")
        if [[ -n "$dest" && -d "$dest" ]]; then
            cd "$dest"
        else
            builtin cd "$@"
        fi
    fi
}
