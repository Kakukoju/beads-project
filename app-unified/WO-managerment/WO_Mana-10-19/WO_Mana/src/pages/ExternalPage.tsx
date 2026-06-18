import React, { useState, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";

interface Props {
  url: string;
  onBack: () => void;
}

const ExternalPage: React.FC<Props> = ({ url, onBack }) => {
  const [loading, setLoading] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // ✅ 自動全螢幕 & 偵測退出事件
  useEffect(() => {
    const iframe = iframeRef.current;

    // 進入全螢幕
    const enterFullscreen = async () => {
      try {
        if (iframe && !document.fullscreenElement) {
          await iframe.requestFullscreen?.();
        }
      } catch (err) {
        console.warn("⚠️ 無法自動進入全螢幕:", err);
      }
    };

    // 偵測離開全螢幕事件
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        onBack(); // ✅ 自動返回首頁
      }
    };

    enterFullscreen();
    document.addEventListener("fullscreenchange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      // 保險：如果頁面卸載時仍全螢幕 → 退出
      if (document.fullscreenElement) {
        document.exitFullscreen?.();
      }
    };
  }, [onBack]);

  // 安全機制：20 秒後強制隱藏 loading
  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 20000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="relative w-screen h-screen bg-black">
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-white z-10">
          <Loader2 className="w-10 h-10 text-blue-600 animate-spin mb-3" />
          <p className="text-gray-600 font-medium">載入中，請稍候...</p>
        </div>
      )}

      {/* 🔹 直接全螢幕顯示 Streamlit 頁面 */}
      <iframe
        ref={iframeRef}
        src={url}
        title="滴定凍乾紀錄"
        onLoad={() => setLoading(false)}
        allowFullScreen
        allow="
          camera; microphone; clipboard-write; fullscreen; geolocation; usb; payment;
          accelerometer; gyroscope; magnetometer; xr-spatial-tracking; publickey-credentials-get
        "
        className="w-full h-full border-none"
      ></iframe>
    </div>
  );
};

export default ExternalPage;
