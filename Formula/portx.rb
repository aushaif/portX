class Portx < Formula
  desc "Simple localhost tunneling tool - expose local ports to the internet"
  homepage "https://github.com/aushaif/portX"
  url "https://github.com/aushaif/portX.git", branch: "main"
  version "2.2.0"

  depends_on "frpc"

  # Prevent conflicts with the unrelated PortX.app cask
  conflicts_with cask: "portx"

  def install
    # 1. Install CLI modules to libexec
    libexec.install Dir["cli/*"]

    # 2. Symlink the frpc binary from the frpc formula into var/portx/bin/
    frp_bin_dir = var/"portx/bin"
    frp_bin_dir.mkpath
    ln_sf Formula["frpc"].opt_bin/"frpc", frp_bin_dir/"frpc"

    # 3. Create the standalone executable wrapper
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
      os.environ.setdefault("PORTX_FRP_BINARY", "#{Formula["frpc"].opt_bin}/frpc")

      # Import and run the main CLI
      import portx as _portx_main

      if __name__ == "__main__":
          _portx_main.main()
    PYTHON

    # 4. Make wrapper executable
    chmod 0755, bin/"portx"

    # 5. Create runtime directories
    (var/"portx/tunnels").mkpath
    (var/"portx/logs").mkpath
  end

  def post_install
    # Create ~/.portx symlink to Homebrew var directory for convenience
    portx_home = Pathname.new(Dir.home)/".portx"
    portx_var  = var/"portx"
    unless portx_home.exist?
      portx_home.make_symlink(portx_var)
      ohai "Created ~/.portx → #{portx_var}"
    end
  end

  def caveats
    <<~EOS
      PortX CLI is installed and ready to use!

      Runtime data is stored in:
        #{var}/portx/

      A convenience symlink is created at:
        ~/.portx → #{var}/portx

      Set your auth token before first use:
        portx api <your-token>

      To create tunnels:
        portx http 8080               # HTTP tunnel
        portx tcp 25565 --p 25565     # TCP (e.g. Minecraft)
        portx udp 19132 --p 19132     # UDP (e.g. Minecraft Bedrock)
        portx list                    # View all tunnels

      Note: This is the PortX CLI tunneling tool.
      It is NOT related to the unrelated PortX.app cask.
    EOS
  end

  test do
    assert_match "PortX", shell_output("#{bin}/portx --help 2>&1")
  end
end
