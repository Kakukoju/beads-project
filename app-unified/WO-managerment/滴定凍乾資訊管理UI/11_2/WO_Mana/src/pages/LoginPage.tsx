// src/pages/LoginPage.tsx
import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = {
  onLogin: (username: string) => void;
};

const LoginPage: React.FC<Props> = ({ onLogin }) => {
  const [username, setUsername] = useState("");

  const handleLogin = () => {
    if (username.trim()) {
      localStorage.setItem("username", username);
      onLogin(username);
    } else {
      alert("請輸入使用者名稱");
    }
  };

  return (
    <div className="flex flex-col justify-center items-center h-screen bg-gradient-to-br from-blue-50 to-blue-100">
      <div className="bg-white p-10 rounded-2xl shadow-2xl w-[400px] text-center">
        <h1 className="text-3xl font-extrabold mb-8 text-gray-800">
          滴定凍乾資訊管理系統
        </h1>
        <Input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="請輸入您的姓名"
          className="mb-6 text-center text-lg"
        />
        <Button
          onClick={handleLogin}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white text-lg py-2"
        >
          進入系統
        </Button>
      </div>
      <p className="text-gray-500 mt-6 text-sm">© 2025 SKYLA 滴定凍乾系統</p>
    </div>
  );
};

export default LoginPage;
