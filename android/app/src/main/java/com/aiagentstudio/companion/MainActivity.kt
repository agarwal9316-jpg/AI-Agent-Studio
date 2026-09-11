package com.aiagentstudio.companion

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.aiagentstudio.companion.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        val versionName = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "1.27.85"
        } catch (_: Exception) { "1.27.85" }
        binding.versionText.text = getString(R.string.version_fmt, versionName)

        binding.webView.settings.javaScriptEnabled = false
        binding.webView.webViewClient = WebViewClient()
        binding.webView.loadDataWithBaseURL(
            null,
            ABOUT_HTML,
            "text/html",
            "UTF-8",
            null
        )

        binding.btnCheckUpdates.setOnClickListener {
            with(UpdateChecker) { checkUpdates(manual = true) }
        }
        binding.btnReleases.setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(UpdateChecker.RELEASES_PAGE_URL)))
        }
        binding.btnPcGuide.setOnClickListener {
            startActivity(
                Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://github.com/agarwal9316-jpg/AI-Agent-Studio#quick-start-windows-pc")
                )
            )
        }
        binding.btnDocs.setOnClickListener {
            startActivity(
                Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://github.com/agarwal9316-jpg/AI-Agent-Studio/tree/main/docs")
                )
            )
        }

        binding.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_check_updates -> {
                    with(UpdateChecker) { checkUpdates(manual = true) }; true
                }
                else -> false
            }
        }
        binding.toolbar.inflateMenu(R.menu.main_menu)

        with(UpdateChecker) { checkUpdates(manual = false) }
    }

    companion object {
        private const val ABOUT_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
body{font-family:sans-serif;padding:12px;background:#0f1115;color:#e8eaed;line-height:1.45}
h1{font-size:1.25rem;margin:0 0 8px;color:#8ab4f8}
h2{font-size:1.05rem;margin:16px 0 6px;color:#c4c7c5}
code{background:#1e222a;padding:1px 4px;border-radius:4px}
ul{padding-left:1.2rem}
.card{background:#1a1d24;border-radius:10px;padding:12px;margin:10px 0}
</style></head><body>
<h1>AI Agent Studio</h1>
<div class="card">
<p>Portable <b>Windows</b> multi-agent studio (CustomTkinter): chat, company workflows, tools, RAG, browser automation.</p>
<p>This Android app is a <b>companion</b> — check updates, open Releases (PC ZIP + APK), and docs.</p>
</div>
<h2>PC how-to</h2>
<ul>
<li>Install Python 3.11+</li>
<li>Unzip the release</li>
<li>Double-click <code>Start.bat</code> or <code>Launch.bat</code></li>
</ul>
<h2>Update check</h2>
<p>Uses GitHub Releases API, with fallback to <code>android/latest-release.json</code> on rate limits.</p>
</body></html>
"""
    }
}
