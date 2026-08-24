class Portx < Formula
  desc "Localhost tunneling tool via PortX server"
  homepage "https://github.com/aushaif/portX"
  url "https://github.com/aushaif/portX/archive/refs/heads/main.tar.gz"
  version "2.0.0"

  depends_on "python@3.10"

  def install
    # 1. Install CLI source code to libexec
    libexec.install Dir["*"]

    # 2. Setup the wrapper script in bin
    # We must ensure that the wrapper script points to the python inside libexec
    (bin/"portx").write <<~EOS
      #!/bin/bash
      export PORTX_FRP_BINARY="#{libexec}/bin/frpc"
      exec python3 "#{libexec}/cli/portx.py" "$@"
    EOS

    # 3. Download the FRP binary specific to the architecture
    frp_version = "0.71.0"
    
    if OS.mac? && Hardware::CPU.arm?
      frp_url = "https://github.com/fatedier/frp/releases/download/v#{frp_version}/frp_#{frp_version}_darwin_arm64.tar.gz"
    elsif OS.mac? && Hardware::CPU.intel?
      frp_url = "https://github.com/fatedier/frp/releases/download/v#{frp_version}/frp_#{frp_version}_darwin_amd64.tar.gz"
    elsif OS.linux? && Hardware::CPU.arm?
      frp_url = "https://github.com/fatedier/frp/releases/download/v#{frp_version}/frp_#{frp_version}_linux_arm64.tar.gz"
    elsif OS.linux? && Hardware::CPU.intel?
      frp_url = "https://github.com/fatedier/frp/releases/download/v#{frp_version}/frp_#{frp_version}_linux_amd64.tar.gz"
    else
      odie "Unsupported architecture"
    end

    system "curl", "-fsSL", "-o", "frp.tar.gz", frp_url
    system "tar", "-xzf", "frp.tar.gz"
    
    frp_dir = Dir["frp_*"].first
    (libexec/"bin").install "#{frp_dir}/frpc"
  end

  def caveats
    <<~EOS
      PortX is installed and ready to use!

      To create an HTTP tunnel:
        portx http 8080

      State and configurations are stored in ~/.portx/
    EOS
  end

  test do
    system "#{bin}/portx", "help"
  end
end
