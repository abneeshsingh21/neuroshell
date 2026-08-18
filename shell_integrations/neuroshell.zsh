# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
# NeuroShell Zsh Semantic Shell Integration

if [[ -n "$NEUROSHELL_SHELL_INTEGRATION_ACTIVE" ]]; then
    return
fi
export NEUROSHELL_SHELL_INTEGRATION_ACTIVE=1

# Semantic Prompt Markers (OSC 133)
neuroshell_prompt_start() {
    printf "\033]133;A\007"
}

neuroshell_command_start() {
    printf "\033]133;C\007"
}

neuroshell_command_executed() {
    local exit_code=$?
    printf "\033]133;D;%s\007" "$exit_code"
    # Inform NeuroShell of current working directory
    printf "\033]7;file://%s%s\007" "$HOST" "$PWD"
}

# Register Zsh hooks
autoload -Uz add-zsh-hook
add-zsh-hook precmd neuroshell_command_executed
add-zsh-hook preexec neuroshell_command_start

# Enable inline directory jumping alias
z() {
    if [[ $# -eq 0 ]]; then
        neuroshell z
    else
        local dest=$(neuroshell --get-jump "$*")
        if [[ -n "$dest" && -d "$dest" ]]; then
            cd "$dest"
        else
            builtin cd "$@"
        fi
    fi
}
