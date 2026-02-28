# 새 Flutter 화면 생성

`$ARGUMENTS` 이름의 Flutter 화면, Riverpod Provider, GoRouter 라우팅을 일괄 생성하라.

## 생성할 파일 (2~3개) + 수정 파일 (1개)

1. `mobile/lib/screens/{name}/{name}_screen.dart` — ConsumerWidget 화면
2. `mobile/lib/providers/{name}_provider.dart` — AsyncNotifierProvider
3. (필요 시) `mobile/lib/models/{name}.dart` — freezed 모델
4. **수정**: `mobile/lib/router.dart` — GoRouter 라우트 등록

## 화면 기본 구조 (ConsumerWidget)

```dart
// mobile/lib/screens/{name}/{name}_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/{name}_provider.dart';

class {Name}Screen extends ConsumerWidget {
  const {Name}Screen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch({name}Provider);

    return Scaffold(
      appBar: AppBar(title: const Text('{Title}')),
      body: state.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('오류: $e')),
        data: (data) => _buildContent(context, ref, data),
      ),
    );
  }
}
```

## ⚠️ 로그인 가드 (키워드·알림 관련 화면 필수)

탭3(알림), 키워드 관리 화면처럼 로그인이 필요한 화면:
```dart
@override
Widget build(BuildContext context, WidgetRef ref) {
  final auth = ref.watch(authProvider);
  if (!auth.isLoggedIn) {
    return Scaffold(
      body: Center(
        child: Column(children: [
          const Text('로그인이 필요합니다.'),
          ElevatedButton(
            onPressed: () => context.push('/login'),
            child: const Text('로그인'),
          ),
        ]),
      ),
    );
  }
  // 로그인 상태 UI ...
}
```

탭1(당근 검색), 탭2(번개+중고나라 검색)는 **로그인 불필요** — 가드 없음.

## GoRouter 등록 방법

`mobile/lib/router.dart`에 추가:
```dart
GoRoute(
  path: '/{name}',
  name: '{name}',
  builder: (context, state) => const {Name}Screen(),
),
```

탭 화면(daangn_tab, market_tab, alerts_tab, settings_tab)은 ShellRoute 내부에 위치.
서브 화면(keyword_form, login 등)은 `/` 루트 아래 독립 GoRoute로 추가.

## 상품 카드 탭 → 딥링크 처리

상품 목록을 표시하는 화면이라면 반드시 `deep_link_service.dart` 경유:
```dart
// 상품 카드 onTap
onTap: () => ref.read(deepLinkServiceProvider).openProduct(
  platform: product.source,
  productId: product.id,
),
```

## API 호출 패턴

직접 Dio 호출 금지 — 반드시 `api_service.dart` 경유:
```dart
final products = await ref.read(apiServiceProvider).searchBunjang(keyword: kw);
```
