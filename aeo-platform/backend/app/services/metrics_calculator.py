"""Metrics calculation service for Specta AI analysis."""

import math

from app.schemas.analytics import (
    AnalysisMetrics,
    CitationMetrics,
    PlatformMetric,
    SentimentDistribution,
)
from app.schemas.fetch import FetchResult


class MetricsCalculator:
    """Calculator for Specta AI metrics."""

    def __init__(self, brand_name: str, competitor_names: list[str]):
        """Initialize calculator.

        Args:
            brand_name: Main brand name
            competitor_names: List of competitor names
        """
        self.brand_name = brand_name
        self.competitor_names = competitor_names

    def calculate_all_metrics(
        self,
        fetch_results: list[FetchResult],
    ) -> AnalysisMetrics:
        """Calculate all metrics from fetch results.

        Args:
            fetch_results: List of fetch results

        Returns:
            Complete analysis metrics
        """
        # Filter successful results
        successful_results = [r for r in fetch_results if r.status == "success"]

        # Calculate BWVS
        bwvs_total = self._calculate_bwvs(successful_results)
        bwvs_by_platform = self._calculate_bwvs_by_platform(successful_results)

        # Calculate mention rates
        mention_rate_overall = self._calculate_mention_rate(successful_results)
        mention_rate_by_platform = self._calculate_mention_rate_by_platform(
            successful_results
        )

        # Calculate sentiment
        sentiment_overall = self._calculate_sentiment_distribution(successful_results)
        sentiment_by_platform = self._calculate_sentiment_by_platform(
            successful_results
        )

        # Calculate citation metrics
        citation_metrics = self._calculate_citation_metrics(successful_results)

        # Calculate accuracy (placeholder)
        accuracy_overall = 85.0  # Would need fact-checking logic

        # Build metrics object
        return AnalysisMetrics(
            bwvs_total=bwvs_total,
            bwvs_max=30.0,
            bwvs_percentage=(bwvs_total / 30.0) * 100,
            bwvs_by_platform=bwvs_by_platform,
            bwvs_by_category={},  # Would need question category data
            mention_rate_overall=mention_rate_overall,
            mention_rate_by_platform=mention_rate_by_platform,
            mention_rate_by_category={},
            mention_rate_by_stage={},
            sentiment_overall=sentiment_overall,
            sentiment_by_platform=sentiment_by_platform,
            accuracy_overall=accuracy_overall,
            citation_metrics=citation_metrics,
            category_metrics={},
        )

    def _calculate_bwvs(self, results: list[FetchResult]) -> float:
        """Calculate Brand Weighted Visibility Score.

        Formula: BWVS = Σ(Mention × Sentiment × Position)

        Args:
            results: Fetch results

        Returns:
            BWVS score
        """
        total_score = 0.0

        for result in results:
            # Check if brand is mentioned
            mentioned = self._is_brand_mentioned(result)
            if not mentioned:
                continue

            # Sentiment coefficient
            sentiment = self._analyze_sentiment(result)
            sentiment_score = {"positive": 1.2, "neutral": 1.0, "negative": -1.0}.get(
                sentiment, 1.0
            )

            # Position coefficient
            rank = self._extract_brand_position(result)
            position_score = 1.0 / math.log2(rank + 1) if rank > 0 else 1.0

            total_score += 1.0 * sentiment_score * position_score

        return total_score

    def _calculate_bwvs_by_platform(
        self, results: list[FetchResult]
    ) -> dict[str, PlatformMetric]:
        """Calculate BWVS by platform.

        Args:
            results: Fetch results

        Returns:
            Platform metrics dictionary
        """
        platform_results: dict[str, list[FetchResult]] = {}
        for result in results:
            platform = result.platform.value
            if platform not in platform_results:
                platform_results[platform] = []
            platform_results[platform].append(result)

        metrics = {}
        for platform, platform_data in platform_results.items():
            bwvs = self._calculate_bwvs(platform_data)
            mention_rate = self._calculate_mention_rate(platform_data)
            positive_rate = self._calculate_positive_rate(platform_data)
            official_share = self._calculate_official_share(platform_data)

            metrics[platform] = PlatformMetric(
                platform=platform,
                bwvs_score=bwvs,
                bwvs_max=7.5,
                bwvs_percentage=(bwvs / 7.5) * 100,
                mention_rate=mention_rate,
                positive_rate=positive_rate,
                official_share=official_share,
                rank=1,  # Would need competitive ranking
            )

        return metrics

    def _calculate_mention_rate(self, results: list[FetchResult]) -> float:
        """Calculate mention rate.

        Args:
            results: Fetch results

        Returns:
            Mention rate percentage
        """
        if not results:
            return 0.0

        mentioned_count = sum(1 for r in results if self._is_brand_mentioned(r))
        return (mentioned_count / len(results)) * 100

    def _calculate_mention_rate_by_platform(
        self, results: list[FetchResult]
    ) -> dict[str, float]:
        """Calculate mention rate by platform.

        Args:
            results: Fetch results

        Returns:
            Platform mention rates
        """
        platform_results: dict[str, list[FetchResult]] = {}
        for result in results:
            platform = result.platform.value
            if platform not in platform_results:
                platform_results[platform] = []
            platform_results[platform].append(result)

        return {
            platform: self._calculate_mention_rate(data)
            for platform, data in platform_results.items()
        }

    def _calculate_sentiment_distribution(
        self, results: list[FetchResult]
    ) -> SentimentDistribution:
        """Calculate sentiment distribution.

        Args:
            results: Fetch results

        Returns:
            Sentiment distribution
        """
        sentiments = []
        for result in results:
            if self._is_brand_mentioned(result):
                sentiment = self._analyze_sentiment(result)
                sentiments.append(sentiment)

        if not sentiments:
            return SentimentDistribution(
                positive=0.0, neutral=100.0, negative=0.0, net_sentiment_score=0.0
            )

        positive = sentiments.count("positive") / len(sentiments) * 100
        neutral = sentiments.count("neutral") / len(sentiments) * 100
        negative = sentiments.count("negative") / len(sentiments) * 100
        net_score = positive - negative

        return SentimentDistribution(
            positive=positive,
            neutral=neutral,
            negative=negative,
            net_sentiment_score=net_score,
        )

    def _calculate_sentiment_by_platform(
        self, results: list[FetchResult]
    ) -> dict[str, SentimentDistribution]:
        """Calculate sentiment by platform.

        Args:
            results: Fetch results

        Returns:
            Platform sentiment distributions
        """
        platform_results: dict[str, list[FetchResult]] = {}
        for result in results:
            platform = result.platform.value
            if platform not in platform_results:
                platform_results[platform] = []
            platform_results[platform].append(result)

        return {
            platform: self._calculate_sentiment_distribution(data)
            for platform, data in platform_results.items()
        }

    def _calculate_citation_metrics(
        self, results: list[FetchResult]
    ) -> CitationMetrics:
        """Calculate citation metrics.

        Args:
            results: Fetch results

        Returns:
            Citation metrics
        """
        all_citations = []
        for result in results:
            all_citations.extend(result.search_references)

        total = len(all_citations)
        if total == 0:
            return CitationMetrics(
                total_citations=0,
                unique_domains=0,
                official_domain_share=0.0,
                authority_matrix_share=0.0,
            )

        # Count official citations
        official_count = sum(1 for c in all_citations if c.is_official)

        # Count unique domains
        domains = set()
        for citation in all_citations:
            # Extract domain from URL
            url = citation.url
            domain = url.split("/")[2] if "/" in url else url
            domains.add(domain)

        # Build distribution
        distribution = {
            "official": {
                "count": official_count,
                "percentage": official_count / total * 100,
            },
            "other": {
                "count": total - official_count,
                "percentage": (total - official_count) / total * 100,
            },
        }

        # Top domains
        domain_counts: dict[str, int] = {}
        for citation in all_citations:
            url = citation.url
            domain = url.split("/")[2] if "/" in url else url
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        top_domains = [
            {"domain": domain, "count": count, "percentage": count / total * 100}
            for domain, count in sorted(
                domain_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]

        return CitationMetrics(
            total_citations=total,
            unique_domains=len(domains),
            official_domain_share=official_count / total * 100,
            authority_matrix_share=official_count / total * 100,  # Simplified
            distribution=distribution,
            top_domains=top_domains,
        )

    def _calculate_positive_rate(self, results: list[FetchResult]) -> float:
        """Calculate positive sentiment rate.

        Args:
            results: Fetch results

        Returns:
            Positive rate percentage
        """
        sentiments = []
        for result in results:
            if self._is_brand_mentioned(result):
                sentiment = self._analyze_sentiment(result)
                sentiments.append(sentiment)

        if not sentiments:
            return 0.0

        return sentiments.count("positive") / len(sentiments) * 100

    def _calculate_official_share(self, results: list[FetchResult]) -> float:
        """Calculate official citation share.

        Args:
            results: Fetch results

        Returns:
            Official share percentage
        """
        all_citations = []
        for result in results:
            all_citations.extend(result.search_references)

        if not all_citations:
            return 0.0

        official_count = sum(1 for c in all_citations if c.is_official)
        return official_count / len(all_citations) * 100

    def _is_brand_mentioned(self, result: FetchResult) -> bool:
        """Check if brand is mentioned in result.

        Args:
            result: Fetch result

        Returns:
            True if mentioned
        """
        if not result.answer_text:
            return False
        return self.brand_name.lower() in result.answer_text.lower()

    def _analyze_sentiment(self, result: FetchResult) -> str:
        """Analyze sentiment of result.

        This is a simplified version. In production, use LLM or sentiment model.

        Args:
            result: Fetch result

        Returns:
            Sentiment: positive, neutral, or negative
        """
        if not result.answer_text:
            return "neutral"

        text = result.answer_text.lower()

        # Simple keyword-based sentiment
        positive_words = ["好", "优秀", "推荐", "喜欢", "值得", "高品质", "精美"]
        negative_words = ["差", "不好", "失望", "贵", "不值得", "智商税", "一般"]

        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        return "neutral"

    def _extract_brand_position(self, result: FetchResult) -> int:
        """Extract brand position in result.

        Args:
            result: Fetch result

        Returns:
            Position (1-based), 0 if not found
        """
        if not result.answer_text:
            return 0

        # Simple position extraction - would need more sophisticated logic
        text = result.answer_text.lower()
        brand_pos = text.find(self.brand_name.lower())

        if brand_pos == -1:
            return 0

        # Estimate position based on text location
        if brand_pos < len(text) * 0.2:
            return 1
        elif brand_pos < len(text) * 0.5:
            return 2
        elif brand_pos < len(text) * 0.8:
            return 3
        return 4

    def calculate_competitive_sov(
        self,
        all_brand_results: dict[str, list[FetchResult]],
    ) -> dict[str, float]:
        """Calculate competitive Share of Voice.

        Args:
            all_brand_results: Results for each brand

        Returns:
            SOV index for each brand
        """
        # Calculate BWVS for each brand
        bwvs_scores = {}
        for brand, results in all_brand_results.items():
            calculator = MetricsCalculator(brand, [])
            bwvs_scores[brand] = calculator._calculate_bwvs(results)

        # Calculate SOV
        total_bwvs = sum(bwvs_scores.values())
        if total_bwvs == 0:
            return {brand: 0.0 for brand in bwvs_scores}

        return {brand: score / total_bwvs for brand, score in bwvs_scores.items()}

    def calculate_platform_consistency(
        self,
        platform_metrics: dict[str, PlatformMetric],
    ) -> float:
        """Calculate platform consistency index.

        Args:
            platform_metrics: Metrics by platform

        Returns:
            Consistency index (0-1)
        """
        if len(platform_metrics) < 2:
            return 1.0

        # Calculate variance of mention rates
        mention_rates = [m.mention_rate for m in platform_metrics.values()]
        mean_rate = sum(mention_rates) / len(mention_rates)

        if mean_rate == 0:
            return 1.0

        variance = sum((r - mean_rate) ** 2 for r in mention_rates) / len(mention_rates)
        std_dev = math.sqrt(variance)

        # Consistency is inverse of coefficient of variation
        cv = std_dev / mean_rate if mean_rate > 0 else 0
        consistency = max(0, 1 - cv)

        return consistency
