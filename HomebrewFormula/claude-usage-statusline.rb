class ClaudeUsageStatusline < Formula
  desc "Claude Code status line showing Pro subscription usage"
  homepage "https://github.com/victorstein/claude-code-usage-statusline"
  license "MIT"

  head "https://github.com/victorstein/claude-code-usage-statusline.git", branch: "main"

  # Stable install — update url + sha256 on each release:
  #   curl -L https://github.com/victorstein/claude-code-usage-statusline/archive/refs/tags/vX.Y.Z.tar.gz | shasum -a 256
  #
  # url "https://github.com/victorstein/claude-code-usage-statusline/archive/refs/tags/v1.1.0.tar.gz"
  # sha256 "<run the curl command above to get this>"

  depends_on :macos
  depends_on "python@3"

  def install
    bin.install "claude-usage-statusline.py" => "claude-usage-statusline"
  end

  def caveats
    <<~EOS
      To enable the status line, add to ~/.claude/settings.json:

        {
          "statusLine": {
            "type": "command",
            "command": "claude-usage-statusline"
          }
        }

      Make sure you are logged into claude.ai in Google Chrome before starting
      a Claude Code session — cookies are extracted automatically on first run.

      To clear the usage cache:
        rm -rf ~/.cache/claude-usage/
    EOS
  end

  test do
    output = pipe_output(
      "#{bin}/claude-usage-statusline",
      '{"model":{"display_name":"Opus"},"context_window":{"used_percentage":42}}'
    )
    assert_match "Opus", output
    assert_match "42%", output
  end
end
