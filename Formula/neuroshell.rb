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
    sha256 "f43c334166a8f3cc592d207709d36cb937204d08c8e0040f0ff84769db7817f5"
  end

  on_linux do
    url "https://github.com/abneeshsingh21/neuroshell/releases/download/v5.7.0/NeuroShell-linux-x86_64.tar.gz"
    sha256 "ad177e5ff95a1ef12cd275756bc0efbdb25cd8d1bba212e851bbb1de7bd3f7c1"
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"neuroshell"
  end

  test do
    assert_match "NeuroShell", shell_output("#{bin}/neuroshell --help", 0)
  end
end
