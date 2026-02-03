#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTokアカウントのメタデータ取得ツール（クラウド対応版）
"""

import sys
import subprocess
import json
import csv
from datetime import datetime
import shutil
from pathlib import Path

def get_tiktok_profile(username):
    """TikTokユーザーのプロフィール情報を取得"""
    
    # TikTokユーザーページのURL
    user_url = f"https://www.tiktok.com/@{username}"
    
    # yt-dlpのパスを探す
    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        print("❌ yt-dlpが見つかりません", file=sys.stderr)
        return None
    
    try:
        # プロフィール情報を取得（最初の1本だけ詳細取得）
        result = subprocess.run([
            yt_dlp_path,
            '--skip-download',
            '--print', '%(uploader)s|%(uploader_id)s|%(channel_follower_count)s',
            '--playlist-items', '1',
            user_url
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split('|')
            if len(parts) >= 3:
                return {
                    'username': parts[1],
                    'display_name': parts[0],
                    'followers': parts[2] if parts[2] != 'NA' else '0'
                }
        
        return None
        
    except Exception as e:
        print(f"プロフィール取得エラー: {str(e)}", file=sys.stderr)
        return None

def get_tiktok_user_videos(username):
    """TikTokユーザーの動画一覧を取得"""
    
    # TikTokユーザーページのURL
    user_url = f"https://www.tiktok.com/@{username}"
    
    print(f"取得中: @{username}", file=sys.stderr)
    
    # yt-dlpのパスを探す
    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        print("❌ yt-dlpが見つかりません", file=sys.stderr)
        return []
    
    try:
        # yt-dlpでメタデータ取得（動画はダウンロードしない）
        result = subprocess.run([
            yt_dlp_path,
            '--flat-playlist',
            '--dump-json',
            '--playlist-end', '100',  # 最大100本
            user_url
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"エラー: {result.stderr}", file=sys.stderr)
            return []
        
        # 各行がJSON
        videos = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                video_data = json.loads(line)
                videos.append({
                    'id': video_data.get('id', ''),
                    'title': video_data.get('title', ''),
                    'view_count': video_data.get('view_count', 0),
                    'like_count': video_data.get('like_count', 0),
                    'comment_count': video_data.get('comment_count', 0),
                    'timestamp': video_data.get('timestamp', 0),
                    'url': video_data.get('url', '')
                })
            except:
                continue
        
        return videos
        
    except Exception as e:
        print(f"エラー: {str(e)}", file=sys.stderr)
        return []

def save_to_csv(username, videos, profile=None, output_dir=None):
    """
    CSVファイルに保存
    
    Args:
        username: TikTokユーザー名
        videos: 動画データのリスト
        profile: プロフィール情報（オプション）
        output_dir: 出力ディレクトリ（デフォルト: /tmp）
    
    Returns:
        str: 保存したCSVファイルのパス
    """
    # 出力ディレクトリの設定
    if output_dir is None:
        output_dir = Path('/tmp')
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_file = output_dir / f"/tmp/tiktok_{username}_metadata.csv"
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # ヘッダー
        writer.writerow(['順位', 'タイトル', '再生回数', 'いいね数', 'コメント数', '投稿日時', 'URL'])
        
        # データ行
        for i, video in enumerate(videos, 1):
            # タイムスタンプを日時に変換
            try:
                date_str = datetime.fromtimestamp(video['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            except:
                date_str = ''
            
            writer.writerow([
                i,
                video.get('title', '')[:100],  # 最大100文字
                video.get('view_count', 0),
                video.get('like_count', 0),
                video.get('comment_count', 0),
                date_str,
                video.get('url', '')
            ])
    
    # プロフィール情報をJSONファイルに保存
    if profile:
        json_file = output_dir / f"/tmp/tiktok_{username}_profile.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"プロフィール保存: {json_file}", file=sys.stderr)
    
    print(f"保存完了: {csv_file}", file=sys.stderr)
    return str(csv_file)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使い方: python3 tiktok_metadata.py <username> [output_dir]", file=sys.stderr)
        sys.exit(1)
    
    username = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    # プロフィール情報を取得
    print("プロフィール情報取得中...", file=sys.stderr)
    profile = get_tiktok_profile(username)
    if profile:
        print(f"✅ フォロワー数: {profile['followers']}", file=sys.stderr)
    
    # 動画一覧を取得
    videos = get_tiktok_user_videos(username)
    
    if not videos:
        print("動画が見つかりませんでした", file=sys.stderr)
        sys.exit(1)
    
    csv_file = save_to_csv(username, videos, profile, output_dir)
    print(f"✅ 取得完了: {len(videos)}本", file=sys.stderr)
    sys.exit(0)
