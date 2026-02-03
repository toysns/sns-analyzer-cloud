#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram/TikTok動画の文字起こしツール
"""

import sys
import subprocess
import os
from pathlib import Path
import re
from datetime import datetime
import shutil

def get_shortcode_from_url(url):
    """URLからショートコードを抽出"""
    match = re.search(r'reel/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(1)
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def download_video(url, output_path):
    """動画をダウンロード"""
    try:
        # yt-dlpのパスを探す
        yt_dlp_path = shutil.which('yt-dlp')
        if not yt_dlp_path:
            raise Exception("yt-dlpが見つかりません")
        
        result = subprocess.run(
            [yt_dlp_path, url, '-o', output_path, '--quiet'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise Exception(f"ダウンロード失敗: {result.stderr}")
        
        return True
    except Exception as e:
        print(f"❌ 動画ダウンロードエラー: {str(e)}", file=sys.stderr)
        return False

def extract_audio(video_path, audio_path):
    """動画から音声を抽出"""
    try:
        # ffmpegのパスを探す
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            raise Exception("ffmpegが見つかりません")
        
        result = subprocess.run([
            ffmpeg_path,
            '-i', str(video_path),
            '-vn',
            '-acodec', 'libmp3lame',
            '-q:a', '2',
            str(audio_path),
            '-y',
            '-loglevel', 'quiet'
        ], capture_output=True, timeout=60)
        
        if result.returncode != 0:
            raise Exception("音声抽出失敗")
        
        return True
    except Exception as e:
        print(f"❌ 音声抽出エラー: {str(e)}", file=sys.stderr)
        return False

def transcribe_audio(audio_path, output_dir):
    """音声を文字起こし"""
    try:
        # Whisperで文字起こし
        result = subprocess.run([
            sys.executable, '-m', 'whisper',
            str(audio_path),
            '--language', 'ja',
            '--model', 'base',
            '--output_dir', str(output_dir),
            '--output_format', 'txt'
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            raise Exception(f"文字起こし失敗: {result.stderr}")
        
        # 生成されたテキストファイルを探す
        audio_name = Path(audio_path).stem
        txt_file = output_dir / f"{audio_name}.txt"
        
        if txt_file.exists():
            with open(txt_file, 'r', encoding='utf-8') as f:
                return f.read()
        
        return None
    except Exception as e:
        print(f"❌ 文字起こしエラー: {str(e)}", file=sys.stderr)
        return None

def transcribe_video(url, output_dir=None):
    """
    動画URLから文字起こしを実行
    
    Args:
        url: Instagram/TikTok動画のURL
        output_dir: 出力ディレクトリ（デフォルト: /tmp/instagram_transcripts）
    
    Returns:
        tuple: (文字起こしテキスト, エラーメッセージ)
    """
    # 出力ディレクトリの設定
    if output_dir is None:
        output_dir = Path('/tmp/instagram_transcripts')
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*54)
    print("🎬 Instagram/TikTok動画 → 文字起こし")
    print("="*54 + "\n")
    
    # ショートコードを取得
    shortcode = get_shortcode_from_url(url)
    
    # ファイルパス
    video_path = output_dir / f"video_{shortcode}.mp4"
    audio_path = output_dir / f"audio_{shortcode}.mp3"
    
    try:
        # 1. 動画ダウンロード
        print("📥 動画をダウンロード中...")
        if not download_video(url, str(video_path)):
            return None, "動画のダウンロードに失敗しました"
        print("✅ ダウンロード完了\n")
        
        # 2. 音声抽出
        print("🎵 音声を抽出中...")
        if not extract_audio(video_path, audio_path):
            return None, "音声の抽出に失敗しました"
        print("✅ 音声抽出完了\n")
        
        # 3. 文字起こし
        print("📝 文字起こし中（数秒かかります）...")
        transcript = transcribe_audio(audio_path, output_dir)
        
        if transcript is None:
            return None, "文字起こしに失敗しました"
        
        print("\n✅ 完了！\n")
        print(f"💾 保存場所: {output_dir}\n")
        
        # 一時ファイルを削除（オプション）
        try:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
        except:
            pass
        
        return transcript, None
        
    except Exception as e:
        return None, f"エラー: {str(e)}"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使い方: python3 instagram_transcriber.py [URL]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    transcript, error = transcribe_video(url, output_dir)
    
    if error:
        print(f"\n❌ {error}", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n📝 文字起こし結果:\n{transcript}")
    sys.exit(0)
