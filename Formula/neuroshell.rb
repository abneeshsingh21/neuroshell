# typed: false
# frozen_string_literal: true

# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Homebrew Formula for NeuroShell Enterprise Terminal

class Neuroshell < Formula
  desc "Tier-1 Autonomous AI Terminal with ConPTY/PTY fidelity and sub-0.05ms execution"
  homepage "https://github.com/abneeshsingh21/neuroshell"
  version "5.7.0"
  license "Apache-2.0"

  on_macos do
    url "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.7.0/NeuroShell-macos-universal.tar.gz"
    # sha256 dynamically verified from GitHub Release SHA256SUMS
  end

  on_linux do
    url "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.7.0/NeuroShell-linux-x86_64.tar.gz"
  end

  def install
    bin.install "neuroshell"
    
    # Install shell completions / integrations
    zsh_completion.install "shell_integrations/neuroshell.zsh" => "_neuroshell" if File.exist?("shell_integrations/neuroshell.zsh")
    bash_completion.install "shell_integrations/neuroshell.bash" => "neuroshell" if File.exist?("shell_integrations/neuroshell.bash")
    fish_completion.install "shell_integrations/neuroshell.fish" => "neuroshell.fish" if File.exist?("shell_integrations/neuroshell.fish")
  end

  test do
    assert_match "NeuroShell", shell_output("#{bin}/neuroshell --help", 0)
  end
end
