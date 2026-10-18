package com.zento.courier;

import android.annotation.SuppressLint;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

/**
 * One activity for all three apps (website, admin, rider). The flavour decides which page of the ZENTO server opens
 * (BuildConfig.START_PATH); everything else is the normal web app running inside a WebView.
 */
public class MainActivity extends AppCompatActivity {

    private WebView web;
    private Uri homeUri;
    private ValueCallback<Uri[]> filePathCallback;

    // Photo / ID upload (rider application) goes through the system file chooser.
    private final ActivityResultLauncher<Intent> chooser = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> {
                if (filePathCallback == null) return;
                filePathCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.getResultCode(), result.getData()));
                filePathCallback = null;
            });

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        homeUri = Uri.parse(BuildConfig.BASE_URL + BuildConfig.START_PATH);

        web = new WebView(this);
        web.setBackgroundColor(getColor(R.color.splash_background));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // the apps keep the sign-in token in localStorage
        s.setAllowFileAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + " ZentoApp/" + BuildConfig.FLAVOR);
        web.addJavascriptInterface(new Bridge(), "ZentoBridge");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                String scheme = u.getScheme() == null ? "" : u.getScheme();
                if (scheme.equals("https") || scheme.equals("http")) {
                    if (u.getHost() != null && u.getHost().equalsIgnoreCase(homeUri.getHost())) return false;
                    openExternally(u);               // other websites open in the phone's browser
                    return true;
                }
                if (scheme.equals("blob") || scheme.equals("about") || scheme.equals("data")) return false;
                openExternally(u);                   // tel:, mailto:, WhatsApp, maps ...
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) view.loadUrl("file:///android_asset/offline.html");
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = callback;
                try {
                    chooser.launch(params.createIntent());
                } catch (Exception e) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "Cannot open the file picker.", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        // Parcel PDFs are created in the page as blob: URLs; fetch the bytes in JavaScript and hand them to the app to save.
        web.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (url.startsWith("blob:")) {
                String name = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimeType);
                if (name == null || name.startsWith("downloadfile")) name = "zento-parcel.pdf";
                String js = "(function(){var x=new XMLHttpRequest();x.open('GET','" + url + "',true);x.responseType='blob';"
                        + "x.onload=function(){var r=new FileReader();r.onloadend=function(){ZentoBridge.save(String(r.result).split(',')[1],'"
                        + (mimeType == null ? "application/pdf" : mimeType) + "','" + name.replace("'", "") + "');};r.readAsDataURL(x.response);};x.send();})();";
                web.evaluateJavascript(js, null);
            } else {
                openExternally(Uri.parse(url));
            }
        });

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (web.canGoBack()) {
                    web.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(homeUri.toString());
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.stopLoading();
            web.destroy();
        }
        super.onDestroy();
    }

    private void openExternally(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException ignored) {
            Toast.makeText(this, "No app can open this link.", Toast.LENGTH_SHORT).show();
        }
    }

    /** Methods the web pages may call through window.ZentoBridge. */
    private class Bridge {
        @JavascriptInterface
        public void retry() {
            runOnUiThread(() -> web.loadUrl(homeUri.toString()));
        }

        @JavascriptInterface
        public void save(String base64, String mime, String name) {
            try {
                byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                String safe = name.replaceAll("[^A-Za-z0-9._-]", "_");
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.Downloads.DISPLAY_NAME, safe);
                    v.put(MediaStore.Downloads.MIME_TYPE, mime);
                    v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    Uri out = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                    if (out == null) throw new IllegalStateException("insert failed");
                    try (OutputStream os = getContentResolver().openOutputStream(out)) {
                        os.write(bytes);
                    }
                } else {
                    File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    try (FileOutputStream os = new FileOutputStream(new File(dir, safe))) {
                        os.write(bytes);
                    }
                }
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Saved to Downloads: " + safe, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Could not save the file.", Toast.LENGTH_LONG).show());
            }
        }
    }
}
