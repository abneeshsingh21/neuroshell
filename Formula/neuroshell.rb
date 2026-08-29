# typed: false
# frozen_string_literal: true

# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Homebrew Formula for NeuroShell Enterprise Terminal

class Neuroshell < Formula
  desc "Tier-1 Autonomous AI Terminal with ConPTY/PTY fidelity and sub-0.05ms execution"
  homepage "https://github.com/abneeshsingh21/neuroshell"
  version "5.18.0"
  license "Apache-2.0"

  on_macos do
    url "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.18.0/NeuroShell-macos-universal.tar.gz"
    sha256 "REPLACE_AT_RELEASE" # resolved by scripts/check_packaging_consistency.py render
  end

  on_linux do
    url "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.18.0/NeuroShell-linux-x86_64.tar.gz"
    sha256 "REPLACE_AT_RELEASE" # resolved by scripts/check_packaging_consistency.py render
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"neuroshell"
  end

  test do
    assert_match "NeuroShell", shell_output("#{bin}/neuroshell --help", 0)
  end
end
