//
//  ContentView.swift
//  ReelMind
//
//  Created by Deepti Jain on 01/05/26.
//

import SwiftUI


struct ContentView: View {
    @EnvironmentObject private var auth: AuthSession

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "heart")
                .imageScale(.large)
            Text("You Go Girl 💕!")
            if let email = auth.session?.user.email {
                Text("Signed in as \(email)")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
            Button("Sign out") {
                Task { try? await auth.signOut() }
            }
            .padding(.top, 8)
        }
        .padding()
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthSession())
}
