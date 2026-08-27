class Smorg < Formula
  include Language::Python::Virtualenv

  desc "Keyboard-driven terminal dashboard, one tab per connected integration"
  homepage "https://github.com/ldelvoye/smorg"
  url "${SDIST_URL}"
  sha256 "${SDIST_SHA256}"
  license "MIT"

  depends_on "python@3.13"

  resource "requirements" do
    url "https://github.com/ldelvoye/smorg/releases/download/v${VERSION}/requirements.txt"
    sha256 "${REQUIREMENTS_SHA256}"
  end

  def install
    virtualenv_create(libexec, "python3.13")
    # The venv is created without pip, so drive the brewed Python's pip at it.
    # Direct pip rather than the pip_install helper: the helper builds from
    # source, and hash-pinned wheels are the point here.
    pip = [Formula["python@3.13"].opt_bin/"python3.13", "-m", "pip", "--python=#{libexec}/bin/python"]
    resource("requirements").stage do
      system(*pip, "install", "--require-hashes", "-r", "requirements.txt")
    end
    system(*pip, "install", "--no-deps", ".")
    bin.install_symlink libexec/"bin/smorg"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/smorg --version")
  end
end
