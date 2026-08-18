# typed: false
# frozen_string_literal: true

# NeuroShell Homebrew Formula
# Install via: brew tap abneeshsingh21/neuroshell && brew install neuroshell

class Neuroshell < Formula
  desc "AI-Powered Intelligent Terminal and C++ Acceleration Host"
  homepage "https://github.com/abneeshsingh21/neuroshell"
  url "https://github.com/abneeshsingh21/neuroshell/archive/refs/tags/v5.0.6.tar.gz"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  license "Proprietary"
  head "https://github.com/abneeshsingh21/neuroshell.git", branch: "main"

  depends_on "cmake" => :build

  def install
    system "cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"
    system "cmake", "--build", "build", "--config", "Release"
    bin.install "build/neuroshell"
  end

  test do
    assert_match "NeuroShell", shell_output("#{bin}/neuroshell --help", 0)
  end
end
