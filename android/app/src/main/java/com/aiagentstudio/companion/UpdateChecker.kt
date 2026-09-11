package com.aiagentstudio.companion

import android.content.Intent
import android.net.Uri
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class ReleaseInfo(
    val tagName: String,
    val name: String,
    val body: String,
    val htmlUrl: String,
    val apkUrl: String?
)

object UpdateChecker {
    private const val TAG = "UpdateChecker"
    const val RELEASES_API =
        "https://api.github.com/repos/agarwal9316-jpg/AI-Agent-Studio/releases/latest"
    const val FALLBACK_JSON_URL =
        "https://raw.githubusercontent.com/agarwal9316-jpg/AI-Agent-Studio/main/android/latest-release.json"
    const val RELEASES_PAGE_URL =
        "https://github.com/agarwal9316-jpg/AI-Agent-Studio/releases"
    const val RATE_LIMIT_MESSAGE =
        "GitHub rate limit — try again in a few minutes or open Releases"

    suspend fun fetchLatest(): Result<ReleaseInfo> = withContext(Dispatchers.IO) {
        val apiResult = fetchFromApi()
        if (apiResult.isSuccess) return@withContext apiResult

        val apiError = apiResult.exceptionOrNull()
        if (!shouldTryFallback(apiError)) {
            return@withContext apiResult
        }

        Log.i(TAG, "API failed (${apiError?.message}); trying raw fallback JSON")
        val fallback = fetchFromFallbackJson()
        if (fallback.isSuccess) return@withContext fallback

        val combined = apiError?.message?.takeIf { it.contains("rate limit", ignoreCase = true) }
            ?: fallback.exceptionOrNull()?.message
            ?: apiError?.message
            ?: "Update check failed"
        Result.failure(Exception(combined))
    }

    fun shouldTryFallback(error: Throwable?): Boolean {
        if (error == null) return false
        val msg = error.message.orEmpty()
        if (msg.contains("rate limit", ignoreCase = true)) return true
        if (msg.contains("HTTP 403") || msg.contains("HTTP 429")) return true
        if (!msg.contains("HTTP ")) return true
        return false
    }

    fun httpErrorMessage(code: Int): String = when (code) {
        403, 429 -> RATE_LIMIT_MESSAGE
        else -> "GitHub API HTTP $code"
    }

    private fun fetchFromApi(): Result<ReleaseInfo> {
        return try {
            val conn = (URL(RELEASES_API).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("Accept", "application/vnd.github+json")
                setRequestProperty("User-Agent", "AI-Agent-Studio-Android")
            }
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    return Result.failure(Exception(httpErrorMessage(code)))
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                Result.success(parseApiReleaseJson(text))
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Log.w(TAG, "fetchFromApi failed", e)
            Result.failure(e)
        }
    }

    private fun fetchFromFallbackJson(): Result<ReleaseInfo> {
        return try {
            val conn = (URL(FALLBACK_JSON_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("User-Agent", "AI-Agent-Studio-Android")
            }
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    return Result.failure(Exception("Fallback JSON HTTP $code"))
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                Result.success(parseFallbackJson(text))
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Log.w(TAG, "fetchFromFallbackJson failed", e)
            Result.failure(e)
        }
    }

    fun parseApiReleaseJson(text: String): ReleaseInfo {
        val o = JSONObject(text)
        val tag = o.optString("tag_name", "")
        val name = o.optString("name", tag)
        val body = o.optString("body", "")
        val htmlUrl = o.optString("html_url", RELEASES_PAGE_URL)
        var apkUrl: String? = null
        val assets = o.optJSONArray("assets")
        if (assets != null) {
            for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                val n = a.optString("name", "")
                if (n.endsWith(".apk", ignoreCase = true)) {
                    apkUrl = a.optString("browser_download_url", null)
                    break
                }
            }
        }
        return ReleaseInfo(tag, name, body, htmlUrl, apkUrl)
    }

    fun parseFallbackJson(text: String): ReleaseInfo {
        val o = JSONObject(text)
        val tag = o.optString("tag", o.optString("tagName", ""))
        val versionName = o.optString("versionName", tag.removePrefix("v"))
        return ReleaseInfo(
            tagName = tag.ifEmpty { "v$versionName" },
            name = o.optString("name", "AI Agent Studio $versionName"),
            body = o.optString("notes", o.optString("body", "")),
            htmlUrl = o.optString("htmlUrl", RELEASES_PAGE_URL),
            apkUrl = o.optString("apkUrl", null)?.takeIf { it.isNotBlank() }
        )
    }

    fun isNewer(latestTag: String, currentVersionName: String): Boolean {
        fun parts(s: String): List<Int> =
            s.trim().removePrefix("v").split(Regex("[^0-9]+"))
                .filter { it.isNotEmpty() }
                .map { it.toIntOrNull() ?: 0 }
        val a = parts(latestTag)
        val b = parts(currentVersionName)
        val n = maxOf(a.size, b.size)
        for (i in 0 until n) {
            val x = a.getOrElse(i) { 0 }
            val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    fun AppCompatActivity.checkUpdates(manual: Boolean) {
        lifecycleScope.launch {
            val result = fetchLatest()
            result.fold(
                onSuccess = { info ->
                    val current = try {
                        packageManager.getPackageInfo(packageName, 0).versionName ?: "0"
                    } catch (_: Exception) { "0" }
                    if (isNewer(info.tagName, current)) {
                        AlertDialog.Builder(this@checkUpdates)
                            .setTitle("Update available: ${info.tagName}")
                            .setMessage(info.body.take(800).ifBlank { info.name })
                            .setPositiveButton("Open release") { _, _ ->
                                val url = info.apkUrl ?: info.htmlUrl
                                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                            }
                            .setNegativeButton("Later", null)
                            .show()
                    } else if (manual) {
                        Toast.makeText(this@checkUpdates, "Up to date ($current)", Toast.LENGTH_SHORT).show()
                    }
                },
                onFailure = { e ->
                    if (manual) {
                        Toast.makeText(this@checkUpdates, e.message ?: "Update check failed", Toast.LENGTH_LONG).show()
                    }
                }
            )
        }
    }
}
