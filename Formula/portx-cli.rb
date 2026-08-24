class PortxCli < Formula
  desc "Simple localhost tunneling tool - PortX CLI"
  homepage "https://github.com/aushaif/portX"
  url "https://github.com/aushaif/portX/archive/refs/heads/main.tar.gz"
  version "2.0.0"
  sha256 "" # Will be auto-calculated by Homebrew

  depends_on "python@3.10"

  def install
    # 1. Install CLI modules to libexec
    libexec.install Dir["cli/*"]

    # 2. Create the standalone executable wrapper
    (bin/"portx").write <<~PYTHON
      #!/usr/bin/env python3
      """
      PortX CLI - Homebrew Installation
      """
      from __future__ import annotations
      
      import sys
      from pathlib import Path
      
      # Add libexec to path so we can import CLI modules
      CLI_LIB = Path("#{libexec}")
      if str(CLI_LIB) not in sys.path:
          sys.path.insert(0, str(CLI_LIB))
      
      # Set FRP binary path for Homebrew installation
      import os
      os.environ.setdefault("PORTX_FRP_BINARY", "#{var}/portx/bin/frpc")
      
      # Import and run the main CLI
      import portx as _portx_main
      
      if __name__ == "__main__":
          _portx_main.main()
    PYTHON

    # 3. Make the wrapper executable
    chmod 0755, bin/"portx"

    # 4. Download and install FRP binary to var directory
    frp_version = "0.71.0"
    
    if OS.mac? && Hardware::CPU.arm?
      frp_url = "https://github.com/fatedier/frp/releases/download/v\#{frp_version}/frp_\#{frp_version}_darwin_arm64.tar.gz"
    elsif OS.mac? && Hardware::CPU.intel?
      frp_url = "https://github.com/fatedier/frp/releases/download/v\#{frp_version}/frp_\#{frp_version}_darwin_amd64.tar.gz"
    elsif OS.linux? && Hardware::CPU.arm?
      frp_url = "https://github.com/fatedier/frp/releases/download/v\#{frp_version}/frp_\#{frp_version}_linux_arm64.tar.gz"
    elsif OS.linux? && Hardware::CPU.intel?
      frp_url = "https://github.com/fatedier/frp/releases/download/v\#{frp_version}/frp_\#{frp_version}_linux_amd64.tar.gz"
    else
      odie "Unsupported architecture"
    end

    # Download FRP to a temporary location
    frp_archive = "frp.tar.gz"
    system "curl", "-fsSL", "-o", frp_archive, frp_url
    system "tar", "-xzf", frp_archive
    
    # Find and install frpc binary
    frp_dir = Dir["frp_*"].first
    frp_bin_dir = var/"portx/bin"
    frp_bin_dir.mkpath
    install frp_dir/"frpc", frp_bin_dir/"frpc"
    
    # 5. Create runtime directories
    (var/"portx/tunnels").mkpath
    (var/"portx/logs").mkpath
  end

  def post_install
    # Create ~/.portx symlink to Homebrew var directory for user convenience
    portx_home = Pathname.new(Dir.home)/".portx"
    portx_var = var/"portx"
    
    unless portx_home.exist?
      portx_home.make_symlink(portx_var)
      ohai "Created ~/.portx symlink to #{portx_var}"
    end
  end

  def caveats
    <<~EOS
      PortX CLI is installed and ready to use!

      Runtime data is stored in:
        #{var}/portx/
      
      A convenience symlink is created at:
        ~/.portx -> #{var}/portx

      To create an HTTP tunnel:
        portx http 8080

      To view all tunnels:
        portx list

      Note: This is the PortX CLI tool (tunneling).
      It is NOT related to the PortX.app macOS application.
    EOS
  end

  test do
    system bin/"portx", "--help"
  end
end
