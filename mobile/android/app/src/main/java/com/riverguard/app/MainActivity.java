package com.riverguard.app;

import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AlertDialog;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends BridgeActivity {
    private String pendingDownload;
    private final ActivityResultLauncher<String> saveDocument = registerForActivityResult(
        new ActivityResultContracts.CreateDocument("application/octet-stream"), uri -> {
            String address = pendingDownload;
            pendingDownload = null;
            if (uri != null && address != null) saveDownload(address, uri);
        }
    );

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if (bridge == null) return;
        bridge.setWebViewClient(new BridgeWebViewClient(bridge) {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return navigate(view, request.getUrl());
            }

            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return navigate(view, Uri.parse(url));
            }

            private boolean navigate(WebView view, Uri uri) {
                if (isLocal(uri.toString()) || LocalAddress.isPrivateUrl(uri.toString())) return false;
                if ("https".equals(uri.getScheme())) return super.shouldOverrideUrlLoading(view, uri.toString());
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame() && !isLocal(request.getUrl().toString())) connectionScreen(true);
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                super.onReceivedHttpError(view, request, response);
                if (request.isForMainFrame() && !isLocal(request.getUrl().toString())) connectionScreen(true);
            }
        });
        bridge.getWebView().setDownloadListener((url, userAgent, disposition, mime, length) -> {
            if (!LocalAddress.isPrivateUrl(url) || pendingDownload != null) return;
            pendingDownload = url;
            String name = url.contains("kind=evaluation") ? "RiverGuard-evaluation.csv" :
                url.contains("kind=csv") ? "RiverGuard-readings.csv" :
                url.contains("kind=report") ? "RiverGuard-report.txt" : "RiverGuard-setup.pdf";
            saveDocument.launch(name);
        });
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (isLocal(bridge.getWebView().getUrl())) {
                    finish();
                } else {
                    new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Return to connection screen?")
                        .setMessage("Your saved chats stay on the laptop. Finish any unsaved sensor setup first.")
                        .setNegativeButton("Stay here", null)
                        .setPositiveButton("Connection screen", (dialog, which) -> connectionScreen(false))
                        .show();
                }
            }
        });
    }

    private boolean isLocal(String address) {
        if (address == null || bridge == null) return false;
        Uri actual = Uri.parse(address), local = Uri.parse(bridge.getLocalUrl());
        return local.getScheme().equals(actual.getScheme()) && local.getHost().equals(actual.getHost()) && local.getPort() == actual.getPort();
    }

    private void connectionScreen(boolean error) {
        String url = bridge.getLocalUrl() + "/?change=1" + (error ? "&error=connection" : "");
        bridge.getWebView().post(() -> bridge.getWebView().loadUrl(url));
    }

    private void saveDownload(String address, Uri document) {
        String cookies = CookieManager.getInstance().getCookie(address);
        String agent = bridge.getWebView().getSettings().getUserAgentString();
        Toast.makeText(this, "Saving your download…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            HttpURLConnection connection = null;
            boolean saved = false;
            try {
                connection = (HttpURLConnection) new URL(address).openConnection();
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(120000);
                if (cookies != null) connection.setRequestProperty("Cookie", cookies);
                connection.setRequestProperty("User-Agent", agent);
                if (connection.getResponseCode() != 200) throw new java.io.IOException("Download failed");
                try (InputStream input = connection.getInputStream(); OutputStream output = getContentResolver().openOutputStream(document)) {
                    if (output == null) throw new java.io.IOException("Cannot open destination");
                    byte[] buffer = new byte[16384];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                }
                saved = true;
            } catch (Exception ignored) {
                // Never log session cookies or downloaded personal readings.
            } finally {
                if (connection != null) connection.disconnect();
            }
            boolean complete = saved;
            runOnUiThread(() -> Toast.makeText(this, complete ? "Download saved" : "Download failed. Check the connection and try again.", Toast.LENGTH_LONG).show());
        }, "riverguard-download").start();
    }
}
