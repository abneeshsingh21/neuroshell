# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell High-Density Synthetic Dataset Generator.
Generates 50,000+ domain-specialized natural-language to shell-command pairs/triplets
for fine-tuning Google DeepMind's EmbeddingGemma 2 (270M Text & Code backbone)
with Matryoshka Representation Learning (MRL) and Multiple Negatives Ranking Loss (MNRL).
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Recipe:
    action_id: str
    category: str
    canonical_nl: str
    default_cmd: str
    powershell_cmd: str = ""
    cmd_exe: str = ""
    parameters: dict[str, list[str]] = field(default_factory=dict)
    nl_templates: list[str] = field(default_factory=list)
    hard_negatives: list[str] = field(default_factory=list)
    is_destructive: bool = False
    explanation: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# MASTER CANONICAL ACTION RECIPES
# ══════════════════════════════════════════════════════════════════════════════

RECIPES: list[Recipe] = [
    # ── Docker & Containers ──
    Recipe(
        action_id="docker_cleanup_stopped_and_unused_images",
        category="DOCKER",
        canonical_nl="clean up all stopped docker containers and unused images",
        default_cmd="docker container prune -f && docker image prune -a -f",
        powershell_cmd="docker container prune -f; docker image prune -a -f",
        cmd_exe="docker container prune -f && docker image prune -a -f",
        nl_templates=[
            "clean up all stopped docker containers and unused images",
            "remove stopped containers and prune unused images in docker",
            "prune all inactive docker containers and delete unused images",
            "cleanup unused docker images and all stopped containers",
            "delete exited containers and unused docker images",
            "docker purge stopped containers and unused images",
            "free up docker space by removing unused images and stopped containers",
            "docker prune containers and images",
            "clear all docker stopped containers and unused images",
            "wipe unused docker images and stopped containers",
            "clean docker stopped containers plus unused images",
            "prune docker dead containers and unused dangling images",
            "clean stopped docker containers and remove unused images",
            "delete all stopped containers and clean unused images docker",
        ],
        hard_negatives=[
            "docker system prune -a --volumes -f",
            "docker container stop $(docker ps -q)",
            "docker image rm $(docker images -q)",
            "docker volume prune -f",
        ],
        is_destructive=True,
        explanation="Prunes all exited/stopped containers and removes unused docker images.",
    ),
    Recipe(
        action_id="docker_prune_containers_only",
        category="DOCKER",
        canonical_nl="remove all stopped docker containers",
        default_cmd="docker container prune -f",
        powershell_cmd="docker container prune -f",
        cmd_exe="docker container prune -f",
        nl_templates=[
            "remove all stopped docker containers",
            "clean up stopped containers in docker",
            "prune exited docker containers",
            "delete dead docker containers",
            "docker remove stopped containers",
            "docker prune containers",
            "wipe out all inactive docker containers",
            "clear stopped containers",
        ],
        hard_negatives=[
            "docker container prune -f && docker image prune -a -f",
            "docker stop $(docker ps -q)",
            "docker rm -f $(docker ps -aq)",
        ],
        is_destructive=True,
        explanation="Prunes only stopped and exited docker containers.",
    ),
    Recipe(
        action_id="docker_prune_images_only",
        category="DOCKER",
        canonical_nl="remove all unused and dangling docker images",
        default_cmd="docker image prune -a -f",
        powershell_cmd="docker image prune -a -f",
        cmd_exe="docker image prune -a -f",
        nl_templates=[
            "remove all unused and dangling docker images",
            "delete unused docker images",
            "prune docker images that are not used",
            "clean up unused images in docker",
            "docker image prune all",
            "wipe out unused images docker",
            "free up disk space by deleting unused docker images",
        ],
        hard_negatives=[
            "docker container prune -f",
            "docker rmi -f $(docker images -q)",
            "docker system prune -a --volumes -f",
        ],
        is_destructive=True,
        explanation="Removes all docker images not referenced by any container.",
    ),
    Recipe(
        action_id="docker_prune_system_all",
        category="DOCKER",
        canonical_nl="deep clean all unused docker containers images networks and volumes",
        default_cmd="docker system prune -a --volumes -f",
        powershell_cmd="docker system prune -a --volumes -f",
        cmd_exe="docker system prune -a --volumes -f",
        nl_templates=[
            "deep clean all unused docker containers images networks and volumes",
            "nuke all unused docker resources including volumes",
            "docker full system prune with volumes",
            "completely wipe unused docker containers images and volumes",
            "free maximum disk space in docker system",
            "docker clean everything including volumes",
        ],
        hard_negatives=[
            "docker container prune -f",
            "docker image prune -f",
            "docker volume ls",
        ],
        is_destructive=True,
        explanation="Comprehensive docker cleanup removing containers, networks, images, and anonymous volumes.",
    ),
    Recipe(
        action_id="docker_stop_all_containers",
        category="DOCKER",
        canonical_nl="stop all running docker containers",
        default_cmd="docker stop $(docker ps -q)",
        powershell_cmd="docker ps -q | ForEach-Object { docker stop $_ }",
        cmd_exe="for /f \"tokens=*\" %i in ('docker ps -q') do docker stop %i",
        nl_templates=[
            "stop all running docker containers",
            "shut down every active docker container",
            "halt all running containers",
            "docker stop all",
            "stop every docker container right now",
            "kill all running docker containers gracefully",
        ],
        hard_negatives=[
            "docker kill $(docker ps -q)",
            "docker rm -f $(docker ps -aq)",
            "docker container prune -f",
        ],
        is_destructive=False,
        explanation="Gracefully halts all active containers.",
    ),
    Recipe(
        action_id="docker_run_postgres",
        category="DOCKER",
        canonical_nl="run postgres container in background on port {port}",
        default_cmd="docker run -d --name {name} -p {port}:5432 -e POSTGRES_PASSWORD={password} postgres",
        powershell_cmd="docker run -d --name {name} -p {port}:5432 -e POSTGRES_PASSWORD={password} postgres",
        cmd_exe="docker run -d --name {name} -p {port}:5432 -e POSTGRES_PASSWORD={password} postgres",
        parameters={
            "name": ["postgres", "pg_db", "dev_postgres", "app_db"],
            "port": ["5432", "5433", "54320"],
            "password": ["postgres", "secret", "mysecretpassword", "devpass123"],
        },
        nl_templates=[
            "run postgres container in background on port {port}",
            "start a postgres database docker container on port {port} with password {password}",
            "spin up postgres in docker on port {port}",
            "launch postgres container named {name} on port {port}",
            "create detached postgres container port {port}",
        ],
        hard_negatives=[
            "docker run -d --name redis -p 6379:6379 redis",
            "docker stop postgres",
            "docker rm postgres",
        ],
        is_destructive=False,
        explanation="Runs official PostgreSQL container in detached mode with published port.",
    ),
    Recipe(
        action_id="docker_run_redis",
        category="DOCKER",
        canonical_nl="run redis cache in background on port {port}",
        default_cmd="docker run -d --name {name} -p {port}:6379 redis:alpine",
        powershell_cmd="docker run -d --name {name} -p {port}:6379 redis:alpine",
        cmd_exe="docker run -d --name {name} -p {port}:6379 redis:alpine",
        parameters={
            "name": ["redis", "redis_cache", "dev_redis"],
            "port": ["6379", "6380", "16379"],
        },
        nl_templates=[
            "run redis cache in background on port {port}",
            "start a redis container named {name} on port {port}",
            "spin up redis:alpine in docker on port {port}",
            "launch detached redis container on port {port}",
            "docker run redis on port {port}",
        ],
        hard_negatives=[
            "docker run -d --name memcached memcached",
            "docker stop redis",
            "docker logs redis",
        ],
        is_destructive=False,
        explanation="Runs lightweight Alpine Redis container with port mapping.",
    ),
    Recipe(
        action_id="docker_logs_follow",
        category="DOCKER",
        canonical_nl="follow live logs of container {container}",
        default_cmd="docker logs -f {container}",
        powershell_cmd="docker logs -f {container}",
        cmd_exe="docker logs -f {container}",
        parameters={
            "container": ["backend", "frontend", "api", "postgres", "redis", "nginx", "worker"],
        },
        nl_templates=[
            "follow live logs of container {container}",
            "tail logs of container {container}",
            "stream logs from docker container {container}",
            "docker logs follow {container}",
            "watch logs for {container}",
            "show live output from container {container}",
        ],
        hard_negatives=[
            "docker logs {container} --tail 10",
            "docker inspect {container}",
            "docker top {container}",
        ],
        is_destructive=False,
        explanation="Streams stdout/stderr logs of the target container in real-time.",
    ),
    Recipe(
        action_id="docker_exec_shell",
        category="DOCKER",
        canonical_nl="open interactive bash shell inside container {container}",
        default_cmd="docker exec -it {container} /bin/bash",
        powershell_cmd="docker exec -it {container} /bin/bash",
        cmd_exe="docker exec -it {container} /bin/bash",
        parameters={
            "container": ["web", "api", "database", "app", "worker", "backend"],
        },
        nl_templates=[
            "open interactive bash shell inside container {container}",
            "attach terminal to docker container {container}",
            "exec bash inside {container}",
            "enter docker container {container} with bash",
            "ssh into docker container {container}",
            "run bash in container {container}",
        ],
        hard_negatives=[
            "docker exec {container} sh -c 'ls -la'",
            "docker attach {container}",
            "docker stop {container}",
        ],
        is_destructive=False,
        explanation="Spawns an interactive pseudo-TTY bash session in the container.",
    ),
    Recipe(
        action_id="docker_compose_up_detached",
        category="DOCKER",
        canonical_nl="start all docker compose services in background",
        default_cmd="docker compose up -d",
        powershell_cmd="docker compose up -d",
        cmd_exe="docker compose up -d",
        nl_templates=[
            "start all docker compose services in background",
            "launch docker compose in detached mode",
            "docker compose up detached",
            "spin up all services in docker-compose.yml",
            "start the stack with docker compose",
            "run docker compose services in the background",
        ],
        hard_negatives=[
            "docker compose down",
            "docker compose build",
            "docker compose logs",
        ],
        is_destructive=False,
        explanation="Builds, (re)creates, and starts containers defined in docker-compose.yml detached.",
    ),
    Recipe(
        action_id="docker_compose_down_volumes",
        category="DOCKER",
        canonical_nl="stop and remove all docker compose services and volumes",
        default_cmd="docker compose down -v",
        powershell_cmd="docker compose down -v",
        cmd_exe="docker compose down -v",
        nl_templates=[
            "stop and remove all docker compose services and volumes",
            "tear down docker compose stack including volumes",
            "docker compose down with volume cleanup",
            "shut down compose services and purge volumes",
            "kill docker compose containers and delete attached volumes",
        ],
        hard_negatives=[
            "docker compose down",
            "docker compose stop",
            "docker compose restart",
        ],
        is_destructive=True,
        explanation="Stops containers and removes containers, networks, and named volumes.",
    ),

    # ── Git & Version Control ──
    Recipe(
        action_id="git_undo_last_commit_keep_staged",
        category="GIT",
        canonical_nl="undo last commit and keep my changes staged",
        default_cmd="git reset --soft HEAD~1",
        powershell_cmd="git reset --soft HEAD~1",
        cmd_exe="git reset --soft HEAD~1",
        nl_templates=[
            "undo last commit and keep my changes staged",
            "undo the previous commit but keep files staged",
            "soft reset last commit",
            "roll back last commit without losing staged changes",
            "git undo commit keep staged",
            "revert last commit but leave changes in staging area",
            "undo commit preserve index",
            "step back one commit keeping changes staged",
        ],
        hard_negatives=[
            "git reset --hard HEAD~1",
            "git reset HEAD~1",
            "git revert HEAD",
            "git commit --amend",
        ],
        is_destructive=False,
        explanation="Moves HEAD back one commit while leaving the working tree and index intact.",
    ),
    Recipe(
        action_id="git_undo_last_commit_unstage",
        category="GIT",
        canonical_nl="undo last commit and unstage changes",
        default_cmd="git reset HEAD~1",
        powershell_cmd="git reset HEAD~1",
        cmd_exe="git reset HEAD~1",
        nl_templates=[
            "undo last commit and unstage changes",
            "mixed reset last commit",
            "undo previous commit and leave changes unstaged in working directory",
            "git undo commit unstage",
            "back out last commit and unstage files",
            "uncommit last commit but keep modifications in files",
        ],
        hard_negatives=[
            "git reset --hard HEAD~1",
            "git reset --soft HEAD~1",
            "git checkout HEAD~1",
        ],
        is_destructive=False,
        explanation="Undoes the commit and resets the staging area, preserving files in working directory.",
    ),
    Recipe(
        action_id="git_discard_all_local_changes",
        category="GIT",
        canonical_nl="discard all uncommitted changes across working directory",
        default_cmd="git reset --hard HEAD && git clean -fd",
        powershell_cmd="git reset --hard HEAD; git clean -fd",
        cmd_exe="git reset --hard HEAD && git clean -fd",
        nl_templates=[
            "discard all uncommitted changes across working directory",
            "nuke all local changes and untracked files in git",
            "completely reset git repository to clean head",
            "wipe all uncommitted edits and untracked files",
            "throw away all local modifications and untracked files",
            "hard reset git and delete untracked files",
        ],
        hard_negatives=[
            "git stash",
            "git reset --soft HEAD",
            "git clean -n",
        ],
        is_destructive=True,
        explanation="Resets tracked files to HEAD and forcefully deletes all untracked files and folders.",
    ),
    Recipe(
        action_id="git_unstage_file",
        category="GIT",
        canonical_nl="unstage file {file}",
        default_cmd="git restore --staged {file}",
        powershell_cmd="git restore --staged {file}",
        cmd_exe="git restore --staged {file}",
        parameters={
            "file": ["main.py", "package.json", "config.yaml", "README.md", "src/index.ts", "Dockerfile"],
        },
        nl_templates=[
            "unstage file {file}",
            "remove {file} from staging area",
            "take {file} out of git index",
            "git unstage {file}",
            "reset staged file {file}",
            "cancel staging for {file}",
        ],
        hard_negatives=[
            "git restore {file}",
            "git rm {file}",
            "git add {file}",
        ],
        is_destructive=False,
        explanation="Removes the specified file from the staging area without modifying file contents.",
    ),
    Recipe(
        action_id="git_create_switch_branch",
        category="GIT",
        canonical_nl="create a new branch {branch} and switch to it",
        default_cmd="git checkout -b {branch}",
        powershell_cmd="git checkout -b {branch}",
        cmd_exe="git checkout -b {branch}",
        parameters={
            "branch": ["feature-login", "fix-bug-102", "dev-v2", "hotfix-auth", "experiment-onnx"],
        },
        nl_templates=[
            "create a new branch {branch} and switch to it",
            "create and checkout branch {branch}",
            "make a new git branch called {branch} and move to it",
            "switch to a new branch named {branch}",
            "start new branch {branch}",
            "git new branch {branch} checkout",
        ],
        hard_negatives=[
            "git branch -d {branch}",
            "git checkout {branch}",
            "git branch {branch}",
        ],
        is_destructive=False,
        explanation="Creates a new local branch and checks it out immediately.",
    ),
    Recipe(
        action_id="git_show_graph_oneline",
        category="GIT",
        canonical_nl="show git commit history as a clean one-line graph",
        default_cmd="git log --graph --oneline --decorate --all",
        powershell_cmd="git log --graph --oneline --decorate --all",
        cmd_exe="git log --graph --oneline --decorate --all",
        nl_templates=[
            "show git commit history as a clean one-line graph",
            "display git branch tree in terminal",
            "visualize git log graph",
            "pretty git commit tree",
            "git graph oneline all branches",
            "show git history with ASCII graph",
        ],
        hard_negatives=[
            "git status",
            "git reflog",
            "git shortlog",
        ],
        is_destructive=False,
        explanation="Displays full visual commit history across all branches in compact single-line format.",
    ),
    Recipe(
        action_id="git_push_force_with_lease",
        category="GIT",
        canonical_nl="push current branch with force with lease",
        default_cmd="git push --force-with-lease",
        powershell_cmd="git push --force-with-lease",
        cmd_exe="git push --force-with-lease",
        nl_templates=[
            "push current branch with force with lease",
            "safe force push current branch",
            "git push force with lease",
            "push changes safely overwriting remote history",
            "force push without overwriting unseen remote commits",
        ],
        hard_negatives=[
            "git push --force",
            "git push",
            "git pull",
        ],
        is_destructive=True,
        explanation="Safely updates remote branch only if nobody else pushed in the meantime.",
    ),
    Recipe(
        action_id="git_stash_wip",
        category="GIT",
        canonical_nl="stash changes including untracked files with message {msg}",
        default_cmd="git stash push -u -m \"{msg}\"",
        powershell_cmd="git stash push -u -m \"{msg}\"",
        cmd_exe="git stash push -u -m \"{msg}\"",
        parameters={
            "msg": ["wip", "work in progress", "temporary stash before pull", "save edits"],
        },
        nl_templates=[
            "stash changes including untracked files with message {msg}",
            "save working directory to git stash with label {msg}",
            "git stash untracked files as {msg}",
            "stash all changes and untracked files named {msg}",
            "stash work in progress {msg}",
        ],
        hard_negatives=[
            "git stash drop",
            "git stash pop",
            "git stash clear",
        ],
        is_destructive=False,
        explanation="Saves uncommitted and untracked modifications to a labeled stash entry.",
    ),
    Recipe(
        action_id="git_stash_pop",
        category="GIT",
        canonical_nl="apply and pop the most recent stash",
        default_cmd="git stash pop",
        powershell_cmd="git stash pop",
        cmd_exe="git stash pop",
        nl_templates=[
            "apply and pop the most recent stash",
            "restore last stashed changes and remove from stash list",
            "git stash pop",
            "un-stash most recent changes",
            "reapply last saved stash",
        ],
        hard_negatives=[
            "git stash drop",
            "git stash clear",
            "git stash list",
        ],
        is_destructive=False,
        explanation="Reapplies the top stash entry and drops it from the stash stack.",
    ),

    # ── Process & System Resource Management ──
    Recipe(
        action_id="proc_kill_port",
        category="PROCESS",
        canonical_nl="find what process is using port {port} and kill it",
        default_cmd="fuser -k {port}/tcp",
        powershell_cmd="Get-Process -Id (Get-NetTCPConnection -LocalPort {port}).OwningProcess | Stop-Process -Force",
        cmd_exe="for /f \"tokens=5\" %a in ('netstat -aon ^| find \":{port}\"') do taskkill /F /PID %a",
        parameters={
            "port": ["3000", "8000", "8080", "5000", "4200", "5432", "6379", "9000"],
        },
        nl_templates=[
            "find what process is using port {port} and kill it",
            "kill process listening on port {port}",
            "free up port {port} by terminating the occupying process",
            "stop whatever is running on port {port}",
            "kill port {port}",
            "terminate app holding port {port}",
            "force kill process on port {port}",
        ],
        hard_negatives=[
            "netstat -ano | grep {port}",
            "curl localhost:{port}",
            "ping localhost",
        ],
        is_destructive=True,
        explanation="Finds the process holding the target network port and forcefully terminates it.",
    ),
    Recipe(
        action_id="proc_find_port",
        category="PROCESS",
        canonical_nl="show process listening on port {port}",
        default_cmd="lsof -i:{port}",
        powershell_cmd="Get-NetTCPConnection -LocalPort {port} | Format-Table -AutoSize",
        cmd_exe="netstat -ano | findstr :{port}",
        parameters={
            "port": ["3000", "8080", "443", "80", "5432", "6379", "27017"],
        },
        nl_templates=[
            "show process listening on port {port}",
            "who is using port {port}",
            "check what is running on port {port}",
            "find pid using port {port}",
            "inspect port {port} listener",
        ],
        hard_negatives=[
            "fuser -k {port}/tcp",
            "iptables -A INPUT -p tcp --dport {port} -j DROP",
        ],
        is_destructive=False,
        explanation="Inspects network sockets to identify the PID and program bound to the port.",
    ),
    Recipe(
        action_id="proc_top_memory",
        category="PROCESS",
        canonical_nl="show top 5 memory consuming processes",
        default_cmd="ps aux --sort=-%mem | head -n 6",
        powershell_cmd="Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 -Property Name,Id,WorkingSet64",
        cmd_exe="tasklist /fi \"memusage gt 100000\"",
        nl_templates=[
            "show top 5 memory consuming processes",
            "which processes are using the most ram",
            "list processes taking highest memory",
            "find biggest memory hogs",
            "top 5 ram consumers",
            "display processes sorted by memory usage",
        ],
        hard_negatives=[
            "free -h",
            "vmstat",
            "kill -9 1",
        ],
        is_destructive=False,
        explanation="Sorts all active processes by resident memory footprint and displays top 5.",
    ),
    Recipe(
        action_id="proc_top_cpu",
        category="PROCESS",
        canonical_nl="show top 5 cpu consuming processes",
        default_cmd="ps aux --sort=-%cpu | head -n 6",
        powershell_cmd="Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 -Property Name,Id,CPU",
        cmd_exe="tasklist",
        nl_templates=[
            "show top 5 cpu consuming processes",
            "find processes using the most cpu",
            "top cpu eaters",
            "list highest cpu utilization processes",
            "which app is maxing out my cpu",
        ],
        hard_negatives=[
            "uptime",
            "top",
            "mpstat",
        ],
        is_destructive=False,
        explanation="Lists processes sorted in descending order of CPU load percentage.",
    ),
    Recipe(
        action_id="sys_free_disk_space",
        category="SYSTEM",
        canonical_nl="check free disk space on all mounted drives in human readable format",
        default_cmd="df -h",
        powershell_cmd="Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, VolumeName, @{N='Free(GB)';E={[math]::Round($_.FreeSpace/1GB, 2)}}, @{N='Used(GB)';E={[math]::Round(($_.Size - $_.FreeSpace)/1GB, 2)}}, @{N='Total(GB)';E={[math]::Round($_.Size/1GB, 2)}}, @{N='PercentFree';E={[math]::Round(($_.FreeSpace/$_.Size)*100, 1)}} | Format-Table -AutoSize",
        cmd_exe="powershell -NoProfile -Command \"Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, VolumeName, @{N='Free(GB)';E={[math]::Round($_.FreeSpace/1GB, 2)}}, @{N='Used(GB)';E={[math]::Round(($_.Size - $_.FreeSpace)/1GB, 2)}}, @{N='Total(GB)';E={[math]::Round($_.Size/1GB, 2)}}, @{N='PercentFree';E={[math]::Round(($_.FreeSpace/$_.Size)*100, 1)}} | Format-Table -AutoSize\"",
        nl_templates=[
            "check free disk space on all mounted drives in human readable format",
            "how much hard drive space is left",
            "show available disk storage",
            "check free space on partitions",
            "display filesystem disk utilization",
            "disk space df -h",
        ],
        hard_negatives=[
            "du -sh *",
            "fdisk -l",
            "mkfs.ext4",
        ],
        is_destructive=False,
        explanation="Reports available storage, used capacity, and mountpoints across all volumes.",
    ),
    Recipe(
        action_id="sys_memory_usage",
        category="SYSTEM",
        canonical_nl="show current ram memory usage in human readable format",
        default_cmd="free -h",
        powershell_cmd="Get-CimInstance Win32_OperatingSystem | Select-Object @{Name='TotalGB';Expression={[math]::Round($_.TotalVisibleMemorySize/1MB,2)}},@{Name='FreeGB';Expression={[math]::Round($_.FreePhysicalMemory/1MB,2)}}",
        cmd_exe="systeminfo | findstr /C:\"Total Physical Memory\" /C:\"Available Physical Memory\"",
        nl_templates=[
            "show current ram memory usage in human readable format",
            "how much ram is currently free",
            "check total and used memory",
            "display system ram stats",
            "memory usage free -h",
        ],
        hard_negatives=[
            "cat /proc/cpuinfo",
            "sysctl -a",
            "swapoff -a",
        ],
        is_destructive=False,
        explanation="Displays total, used, free, and cached system RAM in gigabytes/megabytes.",
    ),

    # ── File System & Search ──
    Recipe(
        action_id="fs_find_delete_logs_older_30d",
        category="FILESYSTEM",
        canonical_nl="find all log files older than 30 days and delete them",
        default_cmd="find . -name \"*.log\" -mtime +30 -delete",
        powershell_cmd="Get-ChildItem -Recurse -Filter *.log | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force",
        cmd_exe="forfiles /P . /M *.log /D -30 /C \"cmd /c del @path\"",
        nl_templates=[
            "find all log files older than 30 days and delete them",
            "delete .log files modified more than 30 days ago",
            "cleanup stale logs older than a month",
            "remove logs older than 30 days",
            "purge old log files beyond 30 days",
            "find and delete log files older than 30 days",
        ],
        hard_negatives=[
            "rm -rf *.log",
            "find . -name \"*.log\" -delete",
            "truncate -s 0 *.log",
        ],
        is_destructive=True,
        explanation="Searches recursively for *.log files with mtime > 30 days and removes them.",
    ),
    Recipe(
        action_id="fs_find_large_files",
        category="FILESYSTEM",
        canonical_nl="find all files larger than 100MB and sort by size",
        default_cmd="find . -type f -size +100M -exec ls -lh {} + | sort -k5 -rh",
        powershell_cmd="Get-ChildItem -Recurse -File | Where-Object Length -gt 100MB | Sort-Object Length -Descending | Select-Object -First 10 Name,Length",
        cmd_exe="forfiles /S /M * /C \"cmd /c if @fsize GEQ 104857600 echo @path @fsize\"",
        nl_templates=[
            "find all files larger than 100MB and sort by size",
            "list files taking more than 100 megabytes",
            "find large files over 100mb",
            "show giant files sorted largest first",
            "locate files bigger than 100MB",
        ],
        hard_negatives=[
            "du -sh *",
            "find . -size +100M -delete",
            "ls -la",
        ],
        is_destructive=False,
        explanation="Scans directory tree for files exceeding 100 megabytes and sorts them descending.",
    ),
    Recipe(
        action_id="fs_compress_tar_gz",
        category="FILESYSTEM",
        canonical_nl="compress folder {dir} into archive {out}.tar.gz",
        default_cmd="tar -czvf {out}.tar.gz {dir}",
        powershell_cmd="tar -czvf {out}.tar.gz {dir}",
        cmd_exe="tar -czvf {out}.tar.gz {dir}",
        parameters={
            "dir": ["dist", "build", "src", "logs", "backup", "data"],
            "out": ["release", "archive", "backup_bundle", "export"],
        },
        nl_templates=[
            "compress folder {dir} into archive {out}.tar.gz",
            "tar gzip directory {dir} to {out}.tar.gz",
            "create tar.gz archive of {dir} named {out}",
            "pack folder {dir} into {out}.tar.gz",
            "compress {dir} as tarball {out}.tar.gz",
        ],
        hard_negatives=[
            "tar -xzvf {out}.tar.gz",
            "rm -rf {dir}",
            "zip -r {out}.zip {dir}",
        ],
        is_destructive=False,
        explanation="Creates a gzip-compressed tar archive from the specified directory.",
    ),
    Recipe(
        action_id="fs_compress_zip",
        category="FILESYSTEM",
        canonical_nl="compress folder {dir} into zip archive {out}.zip",
        default_cmd="zip -r {out}.zip {dir}",
        powershell_cmd="Compress-Archive -Path {dir} -DestinationPath {out}.zip -Force",
        cmd_exe="tar -a -c -f {out}.zip {dir}",
        parameters={
            "dir": ["dist", "build", "data", "assets", "public"],
            "out": ["bundle", "package", "release_v1", "backup"],
        },
        nl_templates=[
            "compress folder {dir} into zip archive {out}.zip",
            "create zip file from directory {dir} called {out}.zip",
            "zip folder {dir} to {out}.zip",
            "archive directory {dir} into a zip file",
        ],
        hard_negatives=[
            "unzip {out}.zip",
            "rm -rf {dir}",
        ],
        is_destructive=False,
        explanation="Recursively archives folder contents into standard ZIP format.",
    ),
    Recipe(
        action_id="fs_count_lines_code",
        category="FILESYSTEM",
        canonical_nl="count total lines of code in all {ext} files",
        default_cmd="find . -name \"*.{ext}\" -exec wc -l {} +",
        powershell_cmd="(Get-ChildItem -Recurse -Filter *.{ext} | Get-Content | Measure-Object -Line).Lines",
        cmd_exe="for /f \"tokens=*\" %a in ('dir /s /b *.{ext}') do @type \"%a\" | find /c /v \"\"",
        parameters={
            "ext": ["py", "ts", "js", "cpp", "go", "rs", "java"],
        },
        nl_templates=[
            "count total lines of code in all {ext} files",
            "how many lines of code are in *.{ext} files",
            "measure total loc in {ext} files",
            "wc -l all {ext} files recursively",
            "calculate line count for {ext} files",
        ],
        hard_negatives=[
            "wc -w *.{ext}",
            "rm -f *.{ext}",
        ],
        is_destructive=False,
        explanation="Recursively tallies total newline count across all matching source files.",
    ),

    # ── Network & Connectivity ──
    Recipe(
        action_id="net_get_public_ip",
        category="NETWORK",
        canonical_nl="show my public ip address",
        default_cmd="curl -s https://api.ipify.org",
        powershell_cmd="(Invoke-RestMethod -Uri https://api.ipify.org).Trim()",
        cmd_exe="curl -s https://api.ipify.org",
        nl_templates=[
            "show my public ip address",
            "what is my external ip",
            "get public ip",
            "check external internet ip address",
            "curl ifconfig.me",
            "what is my public facing ip",
        ],
        hard_negatives=[
            "ip addr show",
            "ifconfig",
            "ipconfig",
        ],
        is_destructive=False,
        explanation="Queries public IP echo endpoint via curl to retrieve WAN address.",
    ),
    Recipe(
        action_id="net_test_port_connectivity",
        category="NETWORK",
        canonical_nl="test if port {port} on host {host} is reachable",
        default_cmd="nc -zv {host} {port}",
        powershell_cmd="Test-NetConnection -ComputerName {host} -Port {port}",
        cmd_exe="curl -v telnet://{host}:{port}",
        parameters={
            "host": ["google.com", "github.com", "localhost", "127.0.0.1", "192.168.1.1"],
            "port": ["443", "80", "22", "5432", "8080", "6379"],
        },
        nl_templates=[
            "test if port {port} on host {host} is reachable",
            "check connectivity to {host} on port {port}",
            "ping port {port} on {host}",
            "is port {port} open on {host}",
            "netcat test {host} {port}",
        ],
        hard_negatives=[
            "ping {host}",
            "traceroute {host}",
            "nmap -A {host}",
        ],
        is_destructive=False,
        explanation="Attempts TCP handshake to verify remote port availability without payload.",
    ),
    Recipe(
        action_id="net_flush_dns_cache",
        category="NETWORK",
        canonical_nl="flush local dns resolver cache",
        default_cmd="sudo systemd-resolve --flush-caches",
        powershell_cmd="Clear-DnsClientCache",
        cmd_exe="ipconfig /flushdns",
        nl_templates=[
            "flush local dns resolver cache",
            "clear dns cache",
            "flush dns",
            "reset dns resolver",
            "ipconfig flushdns",
            "purge local dns entries",
        ],
        hard_negatives=[
            "systemctl restart networking",
            "ip route flush cache",
        ],
        is_destructive=False,
        explanation="Clears the operating system's local DNS resolver name lookup cache.",
    ),

    # ── Kubernetes & Cloud ──
    Recipe(
        action_id="k8s_get_pods_namespace",
        category="K8S",
        canonical_nl="list all pods in namespace {ns}",
        default_cmd="kubectl get pods -n {ns}",
        powershell_cmd="kubectl get pods -n {ns}",
        cmd_exe="kubectl get pods -n {ns}",
        parameters={
            "ns": ["default", "production", "staging", "kube-system", "monitoring", "ingress-nginx"],
        },
        nl_templates=[
            "list all pods in namespace {ns}",
            "get pods in namespace {ns}",
            "show running pods under {ns}",
            "kubectl get pods {ns}",
            "check pod status in namespace {ns}",
        ],
        hard_negatives=[
            "kubectl delete pods --all -n {ns}",
            "kubectl get svc -n {ns}",
            "kubectl get deployments -n {ns}",
        ],
        is_destructive=False,
        explanation="Retrieves current pods, status, and restarts for the target Kubernetes namespace.",
    ),
    Recipe(
        action_id="k8s_restart_deployment",
        category="K8S",
        canonical_nl="restart deployment {deploy} in namespace {ns}",
        default_cmd="kubectl rollout restart deployment/{deploy} -n {ns}",
        powershell_cmd="kubectl rollout restart deployment/{deploy} -n {ns}",
        cmd_exe="kubectl rollout restart deployment/{deploy} -n {ns}",
        parameters={
            "deploy": ["web-frontend", "api-gateway", "auth-service", "worker"],
            "ns": ["default", "production", "staging"],
        },
        nl_templates=[
            "restart deployment {deploy} in namespace {ns}",
            "rollout restart deployment {deploy} under {ns}",
            "trigger rolling restart for deployment {deploy} in {ns}",
            "kubectl restart deploy {deploy} {ns}",
        ],
        hard_negatives=[
            "kubectl delete deployment {deploy} -n {ns}",
            "kubectl scale deployment {deploy} --replicas=0 -n {ns}",
        ],
        is_destructive=False,
        explanation="Triggers an orderly rolling restart for pods in the target deployment.",
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC DATASET BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def generate_variations_for_recipe(recipe: Recipe, target_count: int = 50) -> list[dict]:
    """Generates synthetic training pairs and triplets for a single recipe."""
    results: list[dict] = []

    # Parameter substitution helpers
    param_keys = list(recipe.parameters.keys())

    def get_sample_params() -> dict[str, str]:
        p = {}
        for k, vals in recipe.parameters.items():
            p[k] = random.choice(vals)
        return p

    def safe_sub(text: str, p: dict[str, str]) -> str:
        res = text
        for k, v in p.items():
            res = res.replace(f"{{{k}}}", str(v))
        return res

    # 1. Base NL templates with parameter interpolation
    for template in recipe.nl_templates:
        if param_keys:
            # Sample multiple combinations
            for _ in range(max(1, target_count // len(recipe.nl_templates))):
                params = get_sample_params()
                query = safe_sub(template, params)
                pos_cmd = safe_sub(recipe.default_cmd, params)
                pwsh_cmd = safe_sub(recipe.powershell_cmd or recipe.default_cmd, params)
                cmd_cmd = safe_sub(recipe.cmd_exe or recipe.default_cmd, params)

                # Negative sampling
                neg = random.choice(recipe.hard_negatives) if recipe.hard_negatives else "echo 'invalid command'"

                results.append({
                    "action_id": recipe.action_id,
                    "category": recipe.category,
                    "query": query,
                    "target_cmd": pos_cmd,
                    "powershell_cmd": pwsh_cmd,
                    "cmd_cmd": cmd_cmd,
                    "hard_negative": neg,
                    "is_destructive": recipe.is_destructive,
                })
        else:
            neg = random.choice(recipe.hard_negatives) if recipe.hard_negatives else "echo 'invalid command'"
            results.append({
                "action_id": recipe.action_id,
                "category": recipe.category,
                "query": template,
                "target_cmd": recipe.default_cmd,
                "powershell_cmd": recipe.powershell_cmd or recipe.default_cmd,
                "cmd_cmd": recipe.cmd_exe or recipe.default_cmd,
                "hard_negative": neg,
                "is_destructive": recipe.is_destructive,
            })

    # 2. Add conversational variations (e.g. please, how do i, can you, terminal command to)
    prefixes = [
        "please ", "can you ", "how do i ", "what is the command to ",
        "run command to ", "terminal command for ", "i want to ", "help me ",
        "bash command to ", "quick command: ", ""
    ]
    suffixes = [
        "", " please", " right now", " in terminal", " safely", " using cli"
    ]

    base_samples = list(results)
    while len(results) < target_count:
        base = random.choice(base_samples)
        p = random.choice(prefixes)
        s = random.choice(suffixes)
        q = f"{p}{base['query']}{s}".strip()
        new_item = dict(base)
        new_item["query"] = q
        results.append(new_item)

    return results[:target_count]


def build_full_corpus(target_total_samples: int = 50000) -> tuple[list[dict], list[dict]]:
    """Builds the entire multi-domain synthetic dataset and canonical action catalog."""
    corpus: list[dict] = []
    actions_catalog: list[dict] = []

    samples_per_recipe = max(100, target_total_samples // len(RECIPES))

    for recipe in RECIPES:
        actions_catalog.append({
            "action_id": recipe.action_id,
            "category": recipe.category,
            "canonical_nl": recipe.canonical_nl,
            "default_cmd": recipe.default_cmd,
            "powershell_cmd": recipe.powershell_cmd or recipe.default_cmd,
            "cmd_exe": recipe.cmd_exe or recipe.default_cmd,
            "is_destructive": recipe.is_destructive,
            "explanation": recipe.explanation,
        })

        variations = generate_variations_for_recipe(recipe, target_count=samples_per_recipe)
        corpus.extend(variations)

    random.shuffle(corpus)
    return corpus, actions_catalog


def main():
    print("=" * 60)
    print("🧠 NeuroShell Synthetic Dataset & Canonical Recipe Generator")
    print("=" * 60)

    output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "kaggle_dataset"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Generating multi-domain corpus for {len(RECIPES)} canonical recipes...")
    corpus, catalog = build_full_corpus(target_total_samples=50000)
    print(f"[+] Successfully generated {len(corpus):,} training samples across {len(catalog)} canonical actions.")

    # 1. Save training JSONL
    train_file = output_dir / "neuroshell_train.jsonl"
    with open(train_file, "w", encoding="utf-8") as f:
        for item in corpus:
            f.write(json.dumps(item) + "\n")
    print(f"[+] Saved training dataset: {train_file} ({train_file.stat().st_size / (1024*1024):.2f} MB)")

    # 2. Save Canonical Recipe Catalog JSON
    catalog_file = output_dir / "canonical_recipes.json"
    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    print(f"[+] Saved canonical catalog: {catalog_file} ({catalog_file.stat().st_size / 1024:.2f} KB)")

    # 3. Create Kaggle Dataset Metadata
    metadata_file = output_dir / "dataset-metadata.json"
    metadata = {
        "title": "neuroshell-command-corpus",
        "id": "abneeshsingh/neuroshell-command-corpus",
        "licenses": [{"name": "apache-2.0"}]
    }
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"[+] Saved Kaggle dataset metadata: {metadata_file}")

    print("=" * 60)
    print("✅ Phase 1 Dataset Generation Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
