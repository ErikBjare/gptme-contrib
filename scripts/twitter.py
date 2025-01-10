#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10,<3.12"
# dependencies = [
#   "tweepy>=4.14.0",
#   "rich>=13.0.0",
#   "python-dotenv>=1.0.0",
#   "click>=8.0.0",
# ]
# [tool.uv]
# exclude-newer = "2024-01-01T00:00:00Z"
# ///
"""
Twitter Tool - Simple CLI for Twitter operations

This tool supports both OAuth 1.0a and OAuth 2.0 authentication for Twitter API access.

Authentication Methods:

1. OAuth 2.0 (Recommended for @TimeToBuildBob)
   Required environment variables:
   - TWITTER_CLIENT_ID: OAuth 2.0 client ID
   - TWITTER_CLIENT_SECRET: OAuth 2.0 client secret
   - TWITTER_BEARER_TOKEN: Bearer token for read operations

2. OAuth 1.0a (Legacy)
   Required environment variables:
   - TWITTER_API_KEY: OAuth 1.0a API key
   - TWITTER_API_SECRET: OAuth 1.0a API secret
   - TWITTER_ACCESS_TOKEN: OAuth 1.0a access token
   - TWITTER_ACCESS_SECRET: OAuth 1.0a access token secret
   - TWITTER_BEARER_TOKEN: Bearer token for read operations

Usage:
    ./twitter.py post "Hello world!"      # Post a tweet
    ./twitter.py me @TimeToBuildBob       # Read your tweets
    ./twitter.py user @username           # Read another user's tweets
    ./twitter.py replies --since 24h      # Check replies

Authentication Flow:
1. Tries OAuth 2.0 if client credentials are available
2. Falls back to OAuth 1.0a if OAuth 2.0 fails or isn't configured
3. Uses bearer token for read-only operations

For OAuth 2.0 setup:
1. Configure app in Twitter Developer Portal
2. Add callback URL: http://localhost:9876 (for local development)
3. Request scopes: tweet.read, tweet.write, users.read
4. Add client credentials to .env file
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import click
import tweepy
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Initialize rich console
console = Console()


def load_twitter_client(require_auth: bool = False) -> tweepy.Client:
    """Initialize Twitter client with credentials from .env"""
    load_dotenv()

    # Check for bearer token (required for read operations)
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    if not bearer_token:
        console.print("[red]Missing TWITTER_BEARER_TOKEN in .env")
        sys.exit(1)

    # Create client with appropriate authentication
    # Initialize client based on authentication type
    if require_auth:
        api_key = os.getenv("TWITTER_API_KEY")
        api_secret = os.getenv("TWITTER_API_SECRET")

        # Check for OAuth 2.0 client credentials first
        client_id = os.getenv("TWITTER_CLIENT_ID")
        client_secret = os.getenv("TWITTER_CLIENT_SECRET")

        if client_id and client_secret:
            # Use OAuth 2.0 if client credentials are available
            console.print("[yellow]Debug: Using OAuth 2.0 authentication")
            console.print(f"  Client ID: {client_id[:8]}...")
            console.print(f"  Client Secret: {'*' * 8}...")

            # Check for saved OAuth 2.0 access token
            saved_token = os.getenv("TWITTER_OAUTH2_ACCESS_TOKEN")
            if saved_token:
                console.print("[yellow]Using saved OAuth 2.0 access token")
                try:
                    # Create client with saved token
                    client = tweepy.Client(
                        saved_token,
                        wait_on_rate_limit=True,
                    )

                    # Test the token
                    test = client.get_me(user_auth=False)
                    if test.data:
                        console.print(f"[green]Successfully authenticated as @{test.data.username}")
                        return client
                except Exception as e:
                    console.print(f"[yellow]Saved token failed: {e}")
                    console.print("[yellow]Starting new OAuth 2.0 flow...")

            try:
                # Initialize OAuth 2.0 handler
                oauth2_user_handler = tweepy.OAuth2UserHandler(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri="http://localhost:9876",
                    scope=["tweet.read", "tweet.write", "users.read"],
                )

                # Get authorization URL
                auth_url = oauth2_user_handler.get_authorization_url()
                console.print(f"[yellow]Please authorize at: {auth_url}")

                # Get the response code from user
                console.print("[yellow]After authorizing, you'll be redirected to localhost:9876")
                console.print("[yellow]The response code will be in the URL as 'code' parameter")
                console.print("[yellow]Example: http://localhost:9876?code=abcd1234...")
                response_code = input("Enter the response code from URL: ")

                # Get access token
                access_token = oauth2_user_handler.fetch_token(response_code)
                print(f"{access_token=}")

                # Update or save access token to .env
                env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
                with open(env_path, "r") as f:
                    env_lines = f.readlines()

                # Find existing token line
                token_line_idx = None
                for i, line in enumerate(env_lines):
                    if line.startswith("TWITTER_OAUTH2_ACCESS_TOKEN="):
                        token_line_idx = i
                        break

                new_token_line = f"TWITTER_OAUTH2_ACCESS_TOKEN={access_token['access_token']}\n"

                if token_line_idx is not None:
                    # Replace existing token
                    env_lines[token_line_idx] = new_token_line
                    console.print("[yellow]Updated OAuth 2.0 access token in .env")
                else:
                    # Append new token
                    env_lines.extend(["\n# OAuth 2.0 User Context access token\n", new_token_line])
                    console.print("[yellow]Saved new OAuth 2.0 access token to .env")

                # Write back to file
                with open(env_path, "w") as f:
                    f.writelines(env_lines)

                # Create client with OAuth 2.0 User Context authentication
                client = tweepy.Client(
                    access_token["access_token"],  # Pass access token directly as first argument
                    wait_on_rate_limit=True,
                )

                # Test the credentials with OAuth 2.0
                test = client.get_me(user_auth=False)
                if test.data:
                    console.print(f"[green]Successfully authenticated as @{test.data.username}")
                    return client
                else:
                    console.print("[red]Could not get user info after OAuth 2.0 authentication")
                    sys.exit(1)

            except tweepy.TweepyException as e:
                console.print(f"[red]OAuth 2.0 authentication failed: {str(e)}")
                console.print("[yellow]Falling back to OAuth 1.0a...")

        # Fall back to OAuth 1.0a if OAuth 2.0 fails or isn't configured
        console.print("[yellow]Debug: Using OAuth 1.0a authentication")

        # Check for user auth credentials if needed
        auth_vars = ["TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
        missing_auth = [var for var in auth_vars if not os.getenv(var)]
        if missing_auth:
            console.print("[red]This operation requires user authentication.")
            console.print(f"Missing credentials: {', '.join(missing_auth)}")
            sys.exit(1)

        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_secret = os.getenv("TWITTER_ACCESS_SECRET")

        # Debug info for OAuth 1.0a credentials
        console.print("[yellow]Debug: Using OAuth 1.0a authentication")
        console.print(f"  API Key: {api_key[:8]}..." if api_key else "  API Key: Missing")
        console.print(f"  API Secret: {'*' * 8}..." if api_secret else "  API Secret: Missing")
        console.print(f"  Access Token: {access_token[:8]}..." if access_token else "  Access Token: Missing")
        console.print(f"  Access Secret: {'*' * 8}..." if access_secret else "  Access Secret: Missing")

        # Verify all OAuth credentials are present
        if not all([api_key, api_secret, access_token, access_secret]):
            console.print("[red]Error: Missing OAuth credentials")
            missing = []
            if not api_key:
                missing.append("TWITTER_API_KEY")
            if not api_secret:
                missing.append("TWITTER_API_SECRET")
            if not access_token:
                missing.append("TWITTER_ACCESS_TOKEN")
            if not access_secret:
                missing.append("TWITTER_ACCESS_SECRET")
            console.print(f"[red]Missing: {', '.join(missing)}")
            sys.exit(1)

        # Create OAuth 1.0a client
        # First try creating the client
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            wait_on_rate_limit=True,
        )

        # Test the credentials with a simple API call
        console.print("[yellow]Debug: Testing OAuth credentials...")
        test = client.get_me()
        if test.data:
            console.print(f"[green]Successfully authenticated as @{test.data.username}")
        else:
            console.print("[red]Could not get user info after authentication")
            sys.exit(1)

        return client
    else:
        # For read operations, just use bearer token
        console.print("[yellow]Debug: Using bearer token authentication")
        console.print(f"  Bearer token: {bearer_token[:15]}...")

        # Create client with only bearer token
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=None,
            consumer_secret=None,
            access_token=None,
            access_token_secret=None,
            return_type=tweepy.Response,
            wait_on_rate_limit=True,
        )
    return client


def parse_time(timestr: str) -> datetime:
    """Parse time string like '24h', '7d' into datetime"""
    if timestr.endswith("h"):
        hours = int(timestr[:-1])
        return datetime.now() - timedelta(hours=hours)
    elif timestr.endswith("d"):
        days = int(timestr[:-1])
        return datetime.now() - timedelta(days=days)
    else:
        try:
            return datetime.fromisoformat(timestr)
        except ValueError:
            console.print(f"[red]Invalid time format: {timestr}")
            console.print("Use format like '24h', '7d', or ISO format")
            sys.exit(1)


def display_tweets(tweets: tweepy.Response, username: str) -> None:
    """Display tweets in a formatted table"""
    if not tweets.data:
        console.print(f"[yellow]No tweets found for @{username}")
        return

    # Display tweets
    table = Table(show_header=True)
    table.add_column("Time", style="cyan")
    table.add_column("Tweet", style="white")
    table.add_column("Stats", style="green")

    for tweet in tweets.data:
        # Format engagement stats if available
        stats = []
        if hasattr(tweet, "public_metrics"):
            m = tweet.public_metrics
            stats.extend(
                [
                    f"💟 {m['like_count']}" if m["like_count"] > 0 else "    ",
                    f"💬 {m['reply_count']}" if m["reply_count"] > 0 else "    ",
                    f"🔁 {m['retweet_count']}" if m["retweet_count"] > 0 else "    ",
                ]
            )
        stats_str = " ".join(s for s in stats if s)

        table.add_row(
            (tweet.created_at.strftime("%Y-%m-%d %H:%M") if hasattr(tweet, "created_at") else "N/A"),
            tweet.text,
            stats_str,
        )

    console.print(Panel(table, title=f"Recent tweets from @{username}"))


@click.group()
def cli() -> None:
    """Twitter Tool - Simple CLI for Twitter operations"""
    pass


@cli.command()
@click.option("--username", help="Your Twitter username")
@click.option(
    "--limit",
    default=10,
    type=click.IntRange(5, 100),
    help="Number of tweets (5-100)",
)
def me(username: Optional[str], limit: int) -> None:
    """Read your own recent tweets"""
    client = load_twitter_client(require_auth=True)

    if not username:
        # needs user_auth=False to use OAuth 2.0 and not get the "Consumer key must be string or bytes, not NoneType" error
        me = client.get_me(user_auth=False)
        username = me.data.username

    # Remove @ if present
    assert username is not None
    username = username.lstrip("@")
    console.print(f"[yellow]Fetching tweets for @{username}")

    # Get user ID
    try:
        user = client.get_user(username=username)
        if not user.data:
            console.print(f"[red]User @{username} not found")
            sys.exit(1)
    except tweepy.TweepyException as e:
        console.print(f"[red]Error getting user info: {e}")
        sys.exit(1)

    # Get tweets
    try:
        tweets = client.get_users_tweets(
            user.data.id,
            max_results=limit,
            exclude=["retweets", "replies"],
            tweet_fields=["created_at", "public_metrics"],
        )
        display_tweets(tweets, username)
    except tweepy.TweepyException as e:
        console.print(f"[red]Error getting tweets: {e}")
        sys.exit(1)


@cli.command()
@click.argument("text")
@click.option("--reply-to", help="Tweet ID to reply to")
@click.option("--thread", is_flag=True, help="Post as thread (split by ---)")
def post(text: str, reply_to: Optional[str], thread: bool) -> None:
    """Post a tweet (requires OAuth authentication)"""
    client = load_twitter_client(require_auth=True)

    # Handle thread posting
    if thread:
        tweet_texts = text.split("\n---\n")
        reply_to_id: Optional[str] = None

        for tweet_text in tweet_texts:
            # Create tweet and get the response data
            response = client.create_tweet(
                text=tweet_text.strip(),
                in_reply_to_tweet_id=reply_to_id,
                user_auth=False,
            )
            if not response.data:
                console.print("[red]Error: No response data from tweet creation")
                sys.exit(1)

            # Get the ID for the next reply
            tweet_data = response.data
            if not isinstance(tweet_data, dict):
                console.print("[red]Error: Unexpected response data format")
                sys.exit(1)

            reply_to_id = tweet_data.get("id")
            if not reply_to_id:
                console.print("[red]Error: Could not get tweet ID from response")
                sys.exit(1)

            console.print(f"[green]Posted tweet: {tweet_text.strip()}")
    else:
        # Single tweet
        response = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to, user_auth=False)
        if not response.data:
            console.print("[red]Error: No response data from tweet creation")
            sys.exit(1)

        tweet_data = response.data
        if not isinstance(tweet_data, dict):
            console.print("[red]Error: Unexpected response data format")
            sys.exit(1)

        tweet_id = tweet_data.get("id")
        if not tweet_id:
            console.print("[red]Error: Could not get tweet ID from response")
            sys.exit(1)

        console.print(f"[green]Posted tweet: {text}")
        console.print(f"[blue]Tweet ID: {tweet_id}")


@cli.command()
@click.argument("username")
@click.option(
    "--limit",
    default=10,
    type=click.IntRange(5, 100),
    help="Number of tweets (5-100)",
)
def user(username: str, limit: int) -> None:
    """Read any user's tweets (uses bearer token)"""
    client = load_twitter_client(require_auth=False)

    # Remove @ if present
    username = username.lstrip("@")

    # Get user ID with error handling
    try:
        user = client.get_user(username=username)
        if not user.data:
            console.print(f"[red]User @{username} not found")
            sys.exit(1)
    except tweepy.TweepyException as e:
        console.print(f"[red]Error getting user info: {e}")
        sys.exit(1)

    # Get tweets
    try:
        tweets = client.get_users_tweets(
            user.data.id,
            max_results=limit,
            exclude=["retweets", "replies"],
            tweet_fields=["created_at", "public_metrics"],
        )
        display_tweets(tweets, username)
    except tweepy.TweepyException as e:
        console.print(f"[red]Error getting tweets: {e}")
        sys.exit(1)


@cli.command()
@click.argument("username")
@click.option("--since", default="24h", help="Time window (e.g. 24h, 7d)")
@click.option("--limit", default=50, help="Maximum number of mentions to fetch")
def mentions(username: str, since: str, limit: int) -> None:
    """Check mentions of a specific user"""
    client = load_twitter_client(require_auth=False)

    # Remove @ if present
    username = username.lstrip("@")

    # Get user ID
    user = client.get_user(username=username)
    if not user.data:
        console.print(f"[red]User @{username} not found")
        sys.exit(1)

    # Get mentions since the specified time
    start_time = parse_time(since)
    query = f"@{username} -from:{username}"  # Exclude self-mentions
    mentions = client.search_recent_tweets(
        query=query,
        max_results=limit,
        start_time=start_time,
        tweet_fields=["created_at", "author_id", "public_metrics"],
        expansions=["author_id"],
        user_fields=["username"],
    )

    if not mentions.data:
        console.print(f"[yellow]No mentions found for @{username}")
        return

    # Create lookup for user info
    users = {user.id: user for user in mentions.includes["users"]} if mentions.includes else {}

    # Display mentions
    table = Table(show_header=True)
    table.add_column("Time", style="cyan")
    table.add_column("From", style="green")
    table.add_column("Tweet", style="white")
    table.add_column("Stats", style="blue")

    for tweet in mentions.data:
        # Get author username
        author = users.get(tweet.author_id, None)
        author_name = f"@{author.username}" if author else str(tweet.author_id)

        # Format engagement stats
        stats = []
        if hasattr(tweet, "public_metrics"):
            m = tweet.public_metrics
            stats.extend(
                [
                    f"💟 {m['like_count']}" if m["like_count"] > 0 else "",
                    f"💬 {m['reply_count']}" if m["reply_count"] > 0 else "",
                    f"🔁 {m['retweet_count']}" if m["retweet_count"] > 0 else "",
                ]
            )
        stats_str = " ".join(s for s in stats if s)

        table.add_row(
            tweet.created_at.strftime("%Y-%m-%d %H:%M"),
            author_name,
            tweet.text,
            stats_str,
        )

    console.print(Panel(table, title=f"Recent mentions of @{username}"))


@cli.command()
@click.option("--since", default="24h", help="Time window (e.g. 24h, 7d)")
@click.option("--limit", default=50, help="Maximum number of replies to fetch")
def replies(since: str, limit: int) -> None:
    """Check replies to our tweets"""
    client = load_twitter_client(require_auth=True)

    # Get our user ID with OAuth 2.0
    me = client.get_me(user_auth=False)
    if not me.data:
        console.print("[red]Could not get user information")
        sys.exit(1)

    # Get mentions since the specified time
    start_time = parse_time(since)
    mentions = client.get_users_mentions(
        me.data.id,
        max_results=limit,
        start_time=start_time,
        user_auth=False,
        expansions=["author_id", "in_reply_to_user_id"],
        tweet_fields=["created_at", "author_id", "public_metrics"],
    )

    if not mentions.data:
        console.print("[yellow]No replies found")
        return

    # Display mentions
    table = Table(show_header=True)
    table.add_column("Time", style="cyan")
    table.add_column("From", style="green")
    table.add_column("Reply", style="white")

    for mention in mentions.data:
        table.add_row(
            mention.created_at.strftime("%Y-%m-%d %H:%M") if mention.created_at else "N/A",
            f"@{mention.author_id}",
            mention.text,
        )

    console.print(Panel(table, title="Recent Replies"))


@cli.command()
@click.option("--since", default="24h", help="Time window (e.g. 24h, 7d)")
@click.option("--limit", default=50, help="Maximum number of replies to fetch")
def quotes(since: str, limit: int) -> None:
    """Check quotes of our tweets"""
    client = load_twitter_client(require_auth=True)

    # Get our user ID with OAuth 2.0
    me = client.get_me(user_auth=False)
    if not me.data:
        console.print("[red]Could not get user information")
        sys.exit(1)

    # Get quotes since the specified time
    start_time = parse_time(since)
    query = f"url:{me.data.username}"  # Search for tweets containing links to our tweets
    quotes = client.search_recent_tweets(
        query=query,
        max_results=limit,
        start_time=start_time,
        tweet_fields=["created_at", "author_id", "public_metrics"],
        expansions=["author_id"],
        user_fields=["username"],
    )

    if not quotes.data:
        console.print("[yellow]No quotes found")
        return

    # Create lookup for user info
    users = {user.id: user for user in quotes.includes["users"]} if quotes.includes else {}

    # Display quotes in a simpler format
    console.print("\n[bold]Recent Quotes:[/bold]")

    for tweet in quotes.data:
        # Get author username
        author = users.get(tweet.author_id, None)
        author_name = f"@{author.username}" if author else str(tweet.author_id)

        # Format engagement stats
        stats = []
        if hasattr(tweet, "public_metrics"):
            m = tweet.public_metrics
            stats.extend(
                [
                    f"💟 {m['like_count']}" if m["like_count"] > 0 else "",
                    f"💬 {m['reply_count']}" if m["reply_count"] > 0 else "",
                    f"🔁 {m['retweet_count']}" if m["retweet_count"] > 0 else "",
                ]
            )
        stats_str = " ".join(s for s in stats if s)

        # Print tweet details
        console.print(f"\n[cyan]{tweet.created_at.strftime('%Y-%m-%d %H:%M')}[/cyan]")
        console.print(f"[green]From: {author_name}[/green]")
        console.print(f"[white]Quote: {tweet.text}[/white]")
        console.print(f"[blue]Stats: {stats_str}[/blue]")
        console.print(f"[magenta]ID: {tweet.id}[/magenta]")
        console.print("─" * 50)


if __name__ == "__main__":
    cli()